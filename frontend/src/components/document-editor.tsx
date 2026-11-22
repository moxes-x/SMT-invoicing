/**
 * One editor for invoices, quotes and recurring schedules: customer, dates/schedule, line items
 * with a live total, notes. The server recomputes totals; the preview uses the same maths.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2, UserPlus } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Controller, useFieldArray, useForm, useWatch, type UseFormReturn } from "react-hook-form";
import { Link } from "react-router";

import { ApiError } from "@/api/client";
import { useCustomers, useItems } from "@/api/resources";
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
import { addDays, todayISO } from "@/lib/dates";
import {
  currencyPrefix,
  formatMoney,
  lineAmount,
  parseMoney,
  previewTotals,
  toMoneyInput,
} from "@/lib/money";
import { EMPTY_LINE, schemaFor, type EditorMode, type EditorValues } from "@/lib/document-form";
import { CustomerForm } from "@/pages/customers";

const TERMS = {
  invoice: [
    { days: 0, label: "On receipt" },
    { days: 7, label: "7 days" },
    { days: 14, label: "14 days" },
    { days: 30, label: "30 days" },
  ],
  quote: [
    { days: 7, label: "1 week" },
    { days: 14, label: "2 weeks" },
    { days: 30, label: "30 days" },
  ],
};

const DATE_FIELDS = [
  "customer_id",
  "issue_date",
  "due_date",
  "valid_until",
  "start_date",
  "end_date",
  "days_until_due",
  "interval",
  "frequency",
  "send_mode",
] as const;

export function DocumentEditor({
  mode,
  title,
  description,
  initial,
  cancelTo,
  submitLabel = "Save draft",
  whatsappApi = false,
  onSave,
}: {
  mode: EditorMode;
  title: string;
  description?: string;
  initial: EditorValues;
  cancelTo: string;
  submitLabel?: string;
  whatsappApi?: boolean;
  onSave: (values: EditorValues) => Promise<void>;
}) {
  const { data: customers } = useCustomers();
  const { data: items } = useItems();
  const [addingCustomer, setAddingCustomer] = useState(false);
  const [newCustomer, setNewCustomer] = useState<{ id: number; name: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [openDiscounts, setOpenDiscounts] = useState<Set<number>>(
    () => new Set(initial.lines.flatMap((l, i) => (l.discount ? [i] : []))),
  );

  const form = useForm<EditorValues>({
    resolver: zodResolver(schemaFor(mode)),
    defaultValues: initial,
  });

  // Select a customer created from the dialog once its <option> has rendered.
  useEffect(() => {
    if (newCustomer) form.setValue("customer_id", String(newCustomer.id), { shouldValidate: true });
  }, [newCustomer, form]);

  const { fields, append, remove } = useFieldArray({ control: form.control, name: "lines" });
  const { errors, isSubmitting } = form.formState;
  const lines = useWatch({ control: form.control, name: "lines" }) ?? [];
  const currency = useWatch({ control: form.control, name: "currency" });
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
      await onSave(values);
    } catch (err) {
      setFormError(applyServerErrors(err, form));
    }
  });

  return (
    <>
      <form onSubmit={onSubmit} noValidate className="grid gap-4 pb-28">
        <PageHeader title={title} description={description} />

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

            {mode === "recurring" ? (
              <ScheduleFields form={form} whatsappApi={whatsappApi} />
            ) : (
              <DateFields form={form} mode={mode} />
            )}

            <FormField id="currency" label="Currency">
              <Select id="currency" {...form.register("currency")}>
                <option value="ZMW">Kwacha (ZMW)</option>
                <option value="USD">US Dollar (USD)</option>
              </Select>
            </FormField>
            {mode === "invoice" && currency !== "ZMW" && (
              <FormField
                id="exchange_rate"
                label={`Exchange rate (K per ${prefix.trim() || currency + " "}1)`}
                error={errors.exchange_rate?.message}
                hint="Optional. Shows the Kwacha total on the invoice and counts it in Kwacha reports."
              >
                <Input
                  id="exchange_rate"
                  inputMode="decimal"
                  placeholder="e.g. 26.85"
                  aria-invalid={!!errors.exchange_rate}
                  {...form.register("exchange_rate")}
                />
              </FormField>
            )}
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
                  {openDiscounts.has(index) && (
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
                  )}
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
              <Label className="text-muted-foreground text-xs">
                {mode === "recurring" ? "Each invoice" : "Total"}
              </Label>
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
                <Link to={cancelTo}>Cancel</Link>
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Saving…" : submitLabel}
              </Button>
            </div>
          </div>
        </div>
      </form>

      {/* Outside the <form>: nested forms would submit the outer one. */}
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

function DateFields({
  form,
  mode,
}: {
  form: UseFormReturn<EditorValues>;
  mode: "invoice" | "quote";
}) {
  const { errors } = form.formState;
  const issueDate = useWatch({ control: form.control, name: "issue_date" });
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <FormField
          id="issue_date"
          label={mode === "quote" ? "Date" : "Issue date"}
          error={errors.issue_date?.message}
        >
          <Input id="issue_date" type="date" {...form.register("issue_date")} />
        </FormField>
        <FormField
          id="due_date"
          label={mode === "quote" ? "Valid until" : "Due date"}
          error={errors.due_date?.message}
        >
          <Input id="due_date" type="date" {...form.register("due_date")} />
        </FormField>
      </div>
      <div
        className="flex flex-wrap gap-2"
        aria-label={mode === "quote" ? "Valid for" : "Payment terms"}
      >
        {TERMS[mode].map((t) => (
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
    </>
  );
}

function ScheduleFields({
  form,
  whatsappApi,
}: {
  form: UseFormReturn<EditorValues>;
  whatsappApi: boolean;
}) {
  const { errors } = form.formState;
  const frequency = useWatch({ control: form.control, name: "frequency" });
  return (
    <>
      <div className="grid grid-cols-[6rem_1fr] gap-3">
        <FormField id="interval" label="Every" error={errors.interval?.message}>
          <Input
            id="interval"
            inputMode="numeric"
            className="text-right"
            {...form.register("interval")}
          />
        </FormField>
        <FormField id="frequency" label="&nbsp;">
          <Select id="frequency" aria-label="Frequency" {...form.register("frequency")}>
            <option value="weekly">{frequency === "weekly" ? "week(s)" : "week(s)"}</option>
            <option value="monthly">month(s)</option>
          </Select>
        </FormField>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <FormField id="start_date" label="First invoice on" error={errors.start_date?.message}>
          <Input id="start_date" type="date" {...form.register("start_date")} />
        </FormField>
        <FormField id="end_date" label="Stop after (optional)" error={errors.end_date?.message}>
          <Input id="end_date" type="date" {...form.register("end_date")} />
        </FormField>
      </div>
      <FormField
        id="days_until_due"
        label="Payment due after (days)"
        error={errors.days_until_due?.message}
      >
        <Input id="days_until_due" inputMode="numeric" {...form.register("days_until_due")} />
      </FormField>
      <FormField
        id="send_mode"
        label="When an invoice is created"
        hint={
          whatsappApi
            ? undefined
            : "Automatic WhatsApp needs the WhatsApp Business setup on the server."
        }
      >
        <Select id="send_mode" {...form.register("send_mode")}>
          <option value="draft">Save it as a draft for me to check</option>
          <option value="email">Email it to the customer</option>
          <option value="whatsapp" disabled={!whatsappApi}>
            Send it on WhatsApp
          </option>
        </Select>
      </FormField>
    </>
  );
}

function applyServerErrors(err: unknown, form: UseFormReturn<EditorValues>): string | null {
  if (!(err instanceof ApiError))
    return "Something went wrong. Check your connection and try again.";
  let message: string | null = null;
  for (const [key, msgs] of Object.entries(err.fields)) {
    const field = key === "valid_until" ? "due_date" : key;
    if ((DATE_FIELDS as readonly string[]).includes(field) || field === "exchange_rate") {
      form.setError(field as keyof EditorValues, { message: msgs[0] });
    } else if (key === "lines") {
      message ??= "Check the lines.";
    } else {
      message ??= msgs[0] ?? null;
    }
  }
  return message ?? (Object.keys(err.fields).length ? null : err.message);
}

export function EditorLoading({ children }: { children?: ReactNode }) {
  return <p className="text-muted-foreground">{children ?? "Loading…"}</p>;
}
