import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router";
import { z } from "zod";

import { useMe } from "@/api/auth";
import {
  useCustomers,
  useInvoice,
  useItems,
  useSaveInvoice,
  type Invoice,
  type InvoiceLineRequest,
} from "@/api/resources";
import { CustomerForm } from "@/pages/customers";
import { FormField } from "@/components/form-field";
import { MoneyInput } from "@/components/money-input";
import { ErrorNote, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/api/client";
import { addDays, todayISO } from "@/lib/dates";
import {
  currencyPrefix,
  formatMoney,
  lineAmount,
  parseMoney,
  parseQuantity,
  previewTotals,
  toMoneyInput,
} from "@/lib/money";

const money = (msg: string) => z.string().refine((v) => parseMoney(v) !== null, msg);

const lineSchema = z
  .object({
    item: z.number().nullable(),
    description: z.string().trim().min(1, "Describe this line."),
    quantity: z
      .string()
      .refine((v) => (parseQuantity(v) ?? 0n) > 0n, "Quantity must be more than 0."),
    price: money("Enter a price like 150.00").refine(
      (v) => (parseMoney(v) ?? 0) > 0,
      "Price must be more than 0.",
    ),
    discount: z.string().refine((v) => v.trim() === "" || parseMoney(v) !== null, "Invalid amount"),
  })
  .refine(
    (l) => {
      const d = parseMoney(l.discount || "0") ?? 0;
      const p = parseMoney(l.price) ?? 0;
      const q = parseQuantity(l.quantity) ?? 0n;
      return BigInt(d) * 1000n <= q * BigInt(p);
    },
    { path: ["discount"], message: "Discount is more than the line value." },
  );

const schema = z
  .object({
    customer_id: z.string().min(1, "Choose a customer."),
    currency: z.enum(["ZMW", "USD"]),
    issue_date: z.string().min(1, "Pick a date."),
    due_date: z.string().min(1, "Pick a date."),
    notes: z.string(),
    lines: z.array(lineSchema).min(1, "Add at least one line."),
  })
  .refine((v) => v.due_date >= v.issue_date, {
    path: ["due_date"],
    message: "Due date can't be before the issue date.",
  });
type Values = z.infer<typeof schema>;
type LineValues = Values["lines"][number];

const EMPTY_LINE: LineValues = {
  item: null,
  description: "",
  quantity: "1",
  price: "",
  discount: "",
};
const TERMS = [
  { days: 0, label: "On receipt" },
  { days: 7, label: "7 days" },
  { days: 14, label: "14 days" },
  { days: 30, label: "30 days" },
];

function toLineRequests(lines: LineValues[]): InvoiceLineRequest[] {
  return lines.map((l) => ({
    item: l.item,
    description: l.description.trim(),
    quantity: l.quantity.trim(),
    unit_price: parseMoney(l.price) ?? 0,
    discount: parseMoney(l.discount || "0") ?? 0,
  }));
}

function defaults(invoice: Invoice | undefined, customerId: string, currency: string): Values {
  const today = todayISO();
  if (!invoice) {
    return {
      customer_id: customerId,
      currency: currency === "USD" ? "USD" : "ZMW",
      issue_date: today,
      due_date: addDays(today, 14),
      notes: "",
      lines: [EMPTY_LINE],
    };
  }
  return {
    customer_id: String(invoice.customer.id),
    currency: invoice.currency === "USD" ? "USD" : "ZMW",
    issue_date: invoice.issue_date ?? today,
    due_date: invoice.due_date,
    notes: invoice.notes ?? "",
    lines: invoice.lines.map((l) => ({
      item: l.item ?? null,
      description: l.description,
      quantity: String(Number(l.quantity)),
      price: toMoneyInput(l.unit_price),
      discount: l.discount ? toMoneyInput(l.discount) : "",
    })),
  };
}

export function InvoiceEditorPage() {
  const { id } = useParams();
  const invoiceId = id ? Number(id) : undefined;
  const { data: invoice, isLoading } = useInvoice(invoiceId);
  const { data: me } = useMe();
  const [params] = useSearchParams();

  if (invoiceId && isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (invoice?.is_locked) return <Navigate to={`/invoices/${invoice.id}`} replace />;
  return (
    <Editor
      invoice={invoice}
      initial={defaults(
        invoice,
        params.get("customer") ?? "",
        me?.current_business?.default_currency ?? "ZMW",
      )}
    />
  );
}

function Editor({ invoice, initial }: { invoice?: Invoice; initial: Values }) {
  const navigate = useNavigate();
  const save = useSaveInvoice();
  const { data: customers } = useCustomers();
  const { data: items } = useItems();
  const [addingCustomer, setAddingCustomer] = useState(false);
  const [newCustomer, setNewCustomer] = useState<{ id: number; name: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [openDiscounts, setOpenDiscounts] = useState<Set<number>>(
    () => new Set(initial.lines.flatMap((l, i) => (l.discount ? [i] : []))),
  );

  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial });

  // Select a customer created from the dialog once its <option> has rendered.
  useEffect(() => {
    if (newCustomer) form.setValue("customer_id", String(newCustomer.id), { shouldValidate: true });
  }, [newCustomer, form]);
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "lines" });
  const { errors, isSubmitting } = form.formState;
  const lines = useWatch({ control: form.control, name: "lines" }) ?? [];
  const currency = useWatch({ control: form.control, name: "currency" });
  const issueDate = useWatch({ control: form.control, name: "issue_date" });
  const preview = previewTotals(
    lines.map((l) => ({
      quantity: l.quantity,
      unit_price: parseMoney(l.price) ?? 0,
      discount: parseMoney(l.discount || "0") ?? 0,
    })),
  );
  const prefix = currencyPrefix(currency);
  const activeItems = items?.results.filter((i) => i.is_active) ?? [];
  const customerOptions = [
    ...(newCustomer && !customers?.results.some((c) => c.id === newCustomer.id)
      ? [newCustomer]
      : []),
    ...(customers?.results ?? []),
  ];

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      const saved = await save.mutateAsync({
        id: invoice?.id,
        customer_id: Number(values.customer_id),
        currency: values.currency,
        issue_date: values.issue_date,
        due_date: values.due_date,
        notes: values.notes,
        lines: toLineRequests(values.lines),
      });
      navigate(`/invoices/${saved.id}`);
    } catch (err) {
      if (err instanceof ApiError && Array.isArray(err.fields.lines)) {
        setFormError("Check the invoice lines.");
      } else {
        setFormError(applyFieldErrors(err, form.setError) ?? null);
      }
    }
  });

  return (
    <>
      <form onSubmit={onSubmit} noValidate className="grid gap-4 pb-28">
        <PageHeader
          title={invoice ? `Edit ${invoice.number}` : "New invoice"}
          description="Saved as a draft. Nothing is sent until you choose to send it."
        />

        <Card>
          <CardContent className="grid gap-4">
            <FormField id="customer" label="Customer" error={errors.customer_id?.message}>
              <div className="flex gap-2">
                <Controller
                  control={form.control}
                  name="customer_id"
                  render={({ field }) => (
                    <Select id="customer" aria-invalid={!!errors.customer_id} {...field}>
                      <option value="">Choose a customer…</option>
                      {customerOptions.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </Select>
                  )}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label="Add a new customer"
                  onClick={() => setAddingCustomer(true)}
                >
                  <UserPlus />
                </Button>
              </div>
            </FormField>

            <div className="grid grid-cols-2 gap-3">
              <FormField id="issue_date" label="Issue date" error={errors.issue_date?.message}>
                <Input id="issue_date" type="date" {...form.register("issue_date")} />
              </FormField>
              <FormField id="due_date" label="Due date" error={errors.due_date?.message}>
                <Input id="due_date" type="date" {...form.register("due_date")} />
              </FormField>
            </div>
            <div className="flex flex-wrap gap-2" aria-label="Payment terms">
              {TERMS.map((t) => (
                <Button
                  key={t.days}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    form.setValue("due_date", addDays(issueDate || todayISO(), t.days), {
                      shouldValidate: true,
                    })
                  }
                >
                  {t.label}
                </Button>
              ))}
            </div>
            <FormField id="currency" label="Currency">
              <Select id="currency" {...form.register("currency")}>
                <option value="ZMW">Kwacha (ZMW)</option>
                <option value="USD">US Dollar (USD)</option>
              </Select>
            </FormField>
          </CardContent>
        </Card>

        <div className="grid gap-3">
          <h2 className="font-semibold">Items</h2>
          {fields.map((field, index) => {
            const err = errors.lines?.[index];
            const line = lines[index];
            return (
              <Card key={field.id} className="gap-3 py-4">
                <CardContent className="grid gap-3 px-4">
                  {activeItems.length > 0 && (
                    <Select
                      aria-label={`Saved item for line ${index + 1}`}
                      value={line?.item ?? ""}
                      onChange={(e) => {
                        const item = activeItems.find((i) => i.id === Number(e.target.value));
                        form.setValue(`lines.${index}.item`, item?.id ?? null);
                        if (item) {
                          form.setValue(`lines.${index}.description`, item.name, {
                            shouldValidate: true,
                          });
                          form.setValue(`lines.${index}.price`, toMoneyInput(item.unit_price), {
                            shouldValidate: true,
                          });
                        }
                      }}
                    >
                      <option value="">Pick a saved item (optional)</option>
                      {activeItems.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name} · {formatMoney(i.unit_price)}
                        </option>
                      ))}
                    </Select>
                  )}
                  <FormField
                    id={`l${index}-desc`}
                    label="Description"
                    error={err?.description?.message}
                  >
                    <Input
                      id={`l${index}-desc`}
                      aria-invalid={!!err?.description}
                      {...form.register(`lines.${index}.description`)}
                    />
                  </FormField>
                  <div className="grid grid-cols-[5rem_1fr] gap-3">
                    <FormField id={`l${index}-qty`} label="Qty" error={err?.quantity?.message}>
                      <Input
                        id={`l${index}-qty`}
                        inputMode="decimal"
                        className="text-right tabular-nums"
                        aria-invalid={!!err?.quantity}
                        {...form.register(`lines.${index}.quantity`)}
                      />
                    </FormField>
                    <FormField
                      id={`l${index}-price`}
                      label="Unit price"
                      error={err?.price?.message}
                    >
                      <MoneyInput
                        id={`l${index}-price`}
                        prefix={prefix}
                        aria-invalid={!!err?.price}
                        {...form.register(`lines.${index}.price`)}
                      />
                    </FormField>
                  </div>
                  {openDiscounts.has(index) ? (
                    <FormField
                      id={`l${index}-disc`}
                      label="Discount on this line"
                      error={err?.discount?.message}
                    >
                      <MoneyInput
                        id={`l${index}-disc`}
                        prefix={prefix}
                        aria-invalid={!!err?.discount}
                        {...form.register(`lines.${index}.discount`)}
                      />
                    </FormField>
                  ) : null}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex gap-1">
                      {!openDiscounts.has(index) && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setOpenDiscounts(new Set(openDiscounts).add(index))}
                        >
                          Add discount
                        </Button>
                      )}
                      {fields.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => {
                            remove(index);
                            setOpenDiscounts(
                              new Set(
                                [...openDiscounts]
                                  .filter((i) => i !== index)
                                  .map((i) => (i > index ? i - 1 : i)),
                              ),
                            );
                          }}
                        >
                          <Trash2 /> Remove
                        </Button>
                      )}
                    </div>
                    <span
                      className="font-semibold tabular-nums"
                      aria-label={`Line ${index + 1} amount`}
                    >
                      {line
                        ? formatMoney(
                            lineAmount({
                              quantity: line.quantity,
                              unit_price: parseMoney(line.price) ?? 0,
                              discount: parseMoney(line.discount || "0") ?? 0,
                            }),
                            currency,
                          )
                        : null}
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
          {errors.lines?.root?.message && <ErrorNote>{errors.lines.root.message}</ErrorNote>}
          <Button type="button" variant="outline" onClick={() => append(EMPTY_LINE)}>
            <Plus /> Add line
          </Button>
        </div>

        <FormField id="notes" label="Notes for the customer (optional)">
          <Textarea
            id="notes"
            rows={2}
            placeholder="Thank you for your business!"
            {...form.register("notes")}
          />
        </FormField>

        {formError && <ErrorNote>{formError}</ErrorNote>}

        <div className="bg-background/95 fixed inset-x-0 bottom-16 z-20 border-t p-3 backdrop-blur md:bottom-0 md:left-56">
          <div className="mx-auto flex max-w-4xl items-center justify-between gap-3">
            <div>
              <Label className="text-muted-foreground text-xs">Total</Label>
              <p className="text-xl font-bold tabular-nums" data-testid="preview-total">
                {formatMoney(preview.total, currency)}
              </p>
              {preview.discount_total > 0 && (
                <p className="text-muted-foreground text-xs">
                  after {formatMoney(preview.discount_total, currency)} discount
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <Button asChild variant="ghost">
                <Link to={invoice ? `/invoices/${invoice.id}` : "/invoices"}>Cancel</Link>
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Saving…" : "Save draft"}
              </Button>
            </div>
          </div>
        </div>
      </form>
      {/* Outside the invoice <form>: nested forms would submit the outer one. */}
      <Dialog open={addingCustomer} onClose={() => setAddingCustomer(false)} title="New customer">
        {addingCustomer && (
          <CustomerForm
            onDone={(c) => {
              setAddingCustomer(false);
              setNewCustomer({ id: c.id, name: c.name });
            }}
          />
        )}
      </Dialog>
    </>
  );
}

function applyFieldErrors(
  err: unknown,
  setError: ReturnType<typeof useForm<Values>>["setError"],
): string | null {
  if (!(err instanceof ApiError))
    return "Something went wrong. Check your connection and try again.";
  let message: string | null = null;
  for (const [key, msgs] of Object.entries(err.fields)) {
    if (key === "customer_id" || key === "due_date" || key === "issue_date") {
      setError(key, { message: msgs[0] });
    } else {
      message ??= msgs[0] ?? null;
    }
  }
  return message ?? (Object.keys(err.fields).length ? null : err.message);
}
