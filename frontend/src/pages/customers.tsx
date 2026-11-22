import { zodResolver } from "@hookform/resolvers/zod";
import { MessageCircle, Phone, Plus, ScrollText, Search, Users } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";

import { useAccess, useMe } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useCustomers, useDeleteCustomer, useSaveCustomer, type Customer } from "@/api/resources";
import { FormField } from "@/components/form-field";
import { EmptyState, ErrorNote, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrors } from "@/lib/apply-errors";
import { LANGUAGES, useT } from "@/i18n";

const schema = z.object({
  name: z.string().trim().min(1, "Enter the customer's name.").max(200),
  phone: z.string().optional(),
  email: z.union([z.email("Enter a valid email address."), z.literal("")]).optional(),
  address: z.string().optional(),
  notes: z.string().optional(),
  language: z.enum(["en", "bem", "ny"]),
  tpin: z.string().regex(/^(\d{10})?$/, "TPIN is 10 digits (or leave it blank)."),
});
type Values = z.infer<typeof schema>;

export function CustomerForm({
  customer,
  onDone,
}: {
  customer?: Customer;
  onDone: (c: Customer) => void;
}) {
  const save = useSaveCustomer();
  const remove = useDeleteCustomer();
  const { canManage } = useAccess();
  const t = useT();
  const { data: me } = useMe();
  const vatRegistered = me?.current_business?.vat_registered ?? false;
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: customer?.name ?? "",
      phone: customer?.phone ?? "",
      email: customer?.email ?? "",
      address: customer?.address ?? "",
      notes: customer?.notes ?? "",
      language: customer?.language ?? "en",
      tpin: customer?.tpin ?? "",
    },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      onDone(await save.mutateAsync({ ...values, id: customer?.id }));
    } catch (err) {
      setFormError(
        applyApiErrors(err, form.setError, [
          "name",
          "phone",
          "email",
          "address",
          "notes",
          "language",
          "tpin",
        ]),
      );
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <FormField id="c-name" label="Name" error={errors.name?.message}>
        <Input id="c-name" aria-invalid={!!errors.name} {...form.register("name")} />
      </FormField>
      <FormField
        id="c-phone"
        label="WhatsApp number"
        error={errors.phone?.message}
        hint="e.g. 097 123 4567. Used for WhatsApp sending."
      >
        <Input id="c-phone" type="tel" inputMode="tel" {...form.register("phone")} />
      </FormField>
      <FormField id="c-email" label="Email (optional)" error={errors.email?.message}>
        <Input id="c-email" type="email" {...form.register("email")} />
      </FormField>
      <FormField id="c-language" label={t("lang.customer")}>
        <Select id="c-language" {...form.register("language")}>
          {LANGUAGES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </Select>
      </FormField>
      {(vatRegistered || customer?.tpin) && (
        <FormField
          id="c-tpin"
          label="Customer TPIN (optional)"
          error={errors.tpin?.message}
          hint="For business customers. Printed on ZRA tax invoices."
        >
          <Input id="c-tpin" inputMode="numeric" maxLength={10} {...form.register("tpin")} />
        </FormField>
      )}
      <FormField id="c-address" label="Address (optional)" error={errors.address?.message}>
        <Textarea id="c-address" rows={2} {...form.register("address")} />
      </FormField>
      {formError && <ErrorNote>{formError}</ErrorNote>}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
        {customer && canManage ? (
          <Button
            type="button"
            variant="ghost"
            className="text-destructive"
            onClick={async () => {
              if (!window.confirm(`Delete ${customer.name}?`)) return;
              try {
                await remove.mutateAsync(customer.id);
                onDone(customer);
              } catch (err) {
                setFormError(err instanceof ApiError ? err.message : "Couldn't delete.");
              }
            }}
          >
            Delete
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : customer ? "Save changes" : "Add customer"}
        </Button>
      </div>
    </form>
  );
}

export function CustomersPage() {
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Customer | "new" | null>(null);
  const { data, isLoading } = useCustomers(search);
  const { canWrite } = useAccess();
  const t = useT();

  return (
    <div className="grid gap-4">
      <PageHeader
        title={t("nav.customers")}
        actions={
          canWrite && (
            <Button onClick={() => setEditing("new")}>
              <Plus /> {t("action.add")}
            </Button>
          )
        }
      />
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          aria-label="Search customers"
          placeholder="Search by name, phone or email"
          className="pl-9"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {!isLoading && !data?.results.length ? (
        <EmptyState icon={<Users />} title={search ? "No matches" : "No customers yet"}>
          {canWrite && !search && (
            <Button onClick={() => setEditing("new")}>Add your first customer</Button>
          )}
        </EmptyState>
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-y">
            {data?.results.map((c) => (
              <li key={c.id} className="flex items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left disabled:cursor-default"
                  disabled={!canWrite}
                  onClick={() => setEditing(c)}
                >
                  <span className="block truncate font-medium">{c.name}</span>
                  <span className="text-muted-foreground block truncate text-xs">
                    {[c.phone, c.email].filter(Boolean).join(" · ") || "No contact details"}
                  </span>
                </button>
                {c.phone && (
                  <>
                    <Button asChild variant="ghost" size="icon" aria-label={`Call ${c.name}`}>
                      <a href={`tel:${c.phone}`}>
                        <Phone />
                      </a>
                    </Button>
                    <Button asChild variant="ghost" size="icon" aria-label={`WhatsApp ${c.name}`}>
                      <a
                        href={`https://wa.me/${c.phone.replace("+", "")}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <MessageCircle />
                      </a>
                    </Button>
                  </>
                )}
                <Button asChild variant="ghost" size="icon" aria-label={`Statement for ${c.name}`}>
                  <Link to={`/customers/${c.id}/statement`}>
                    <ScrollText />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link to={`/invoices?customer=${c.id}`}>Invoices</Link>
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Dialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New customer" : "Edit customer"}
      >
        {editing !== null && (
          <CustomerForm
            key={editing === "new" ? "new" : editing.id}
            customer={editing === "new" ? undefined : editing}
            onDone={() => setEditing(null)}
          />
        )}
      </Dialog>
    </div>
  );
}
