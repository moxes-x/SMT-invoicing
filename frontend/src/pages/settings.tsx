import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { useMe } from "@/api/auth";
import { useAppConfig, useUpdateBusiness } from "@/api/resources";
import { FormField } from "@/components/form-field";
import { OnlinePaymentsCard } from "@/components/online-payments-card";
import { ErrorNote, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrors } from "@/lib/apply-errors";

const schema = z.object({
  name: z.string().trim().min(1, "Enter your business name.").max(200),
  phone: z.string(),
  email: z.union([z.email("Enter a valid email address."), z.literal("")]),
  address: z.string(),
  tpin: z.string().regex(/^(\d{10})?$/, "TPIN is 10 digits (or leave it blank)."),
  payment_details: z.string().max(1000),
  default_currency: z.enum(["ZMW", "USD"]),
  vat_registered: z.boolean(),
  auto_reminders: z.boolean(),
  reminder_interval_days: z.coerce
    .number<string>()
    .int()
    .min(1, "At least 1 day.")
    .max(60, "At most 60 days."),
  max_reminders: z.coerce.number<string>().int().min(1, "At least 1.").max(10, "At most 10."),
});
type Values = z.infer<typeof schema>;
const FIELDS = [
  "name",
  "phone",
  "email",
  "address",
  "tpin",
  "payment_details",
  "reminder_interval_days",
  "max_reminders",
] as const;

export function SettingsPage() {
  const { data: me } = useMe();
  const business = me?.current_business;
  if (!business) return null;
  const canEdit = business.role === "owner" || business.role === "admin";
  return (
    <div className="grid grid-cols-1 gap-4">
      <BusinessForm key={business.id} />
      <OnlinePaymentsCard key={`lenco-${business.id}`} canEdit={canEdit} />
    </div>
  );
}

function BusinessForm() {
  const { data: me } = useMe();
  const business = me!.current_business!;
  const update = useUpdateBusiness(business.id);
  const [status, setStatus] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const canEdit = business.role === "owner" || business.role === "admin";
  const form = useForm<z.input<typeof schema>, unknown, Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: business.name,
      phone: business.phone ?? "",
      email: business.email ?? "",
      address: business.address ?? "",
      tpin: business.tpin ?? "",
      payment_details: business.payment_details ?? "",
      default_currency: business.default_currency === "USD" ? "USD" : "ZMW",
      vat_registered: business.vat_registered ?? false,
      auto_reminders: business.auto_reminders ?? false,
      reminder_interval_days: String(business.reminder_interval_days ?? 7),
      max_reminders: String(business.max_reminders ?? 3),
    },
  });
  const { errors, isSubmitting, isDirty } = form.formState;
  const whatsappApi = !!useAppConfig().data?.whatsapp_api;
  const autoReminders = useWatch({ control: form.control, name: "auto_reminders" });

  const onSubmit = form.handleSubmit(async (values) => {
    setStatus(null);
    setFormError(null);
    try {
      const saved = await update.mutateAsync(values);
      form.reset({
        ...values,
        phone: saved.phone ?? "",
        reminder_interval_days: String(values.reminder_interval_days),
        max_reminders: String(values.max_reminders),
      });
      setStatus("Saved.");
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, FIELDS));
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <PageHeader
        title="Business settings"
        description="Shown on every invoice and quote you send."
      />
      <Card>
        <CardContent>
          <fieldset disabled={!canEdit} className="grid gap-4">
            <FormField id="b-name" label="Business name" error={errors.name?.message}>
              <Input id="b-name" aria-invalid={!!errors.name} {...form.register("name")} />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="b-phone" label="Phone" error={errors.phone?.message}>
                <Input id="b-phone" type="tel" {...form.register("phone")} />
              </FormField>
              <FormField id="b-email" label="Email" error={errors.email?.message}>
                <Input id="b-email" type="email" {...form.register("email")} />
              </FormField>
            </div>
            <FormField id="b-address" label="Address">
              <Textarea id="b-address" rows={2} {...form.register("address")} />
            </FormField>
            <FormField
              id="b-pay"
              label="How customers pay you"
              error={errors.payment_details?.message}
              hint="Printed on invoices, e.g. MTN MoMo 096 123 4567 (Name), Zanaco Acc 0123456789."
            >
              <Textarea id="b-pay" rows={3} {...form.register("payment_details")} />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="b-tpin" label="TPIN (optional)" error={errors.tpin?.message}>
                <Input id="b-tpin" inputMode="numeric" maxLength={10} {...form.register("tpin")} />
              </FormField>
              <FormField id="b-cur" label="Default currency">
                <Select id="b-cur" {...form.register("default_currency")}>
                  <option value="ZMW">Kwacha (ZMW)</option>
                  <option value="USD">US Dollar (USD)</option>
                </Select>
              </FormField>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-primary size-4"
                {...form.register("vat_registered")}
              />
              We are VAT-registered
            </label>
          </fieldset>
        </CardContent>
      </Card>
      <Card>
        <CardContent>
          <fieldset disabled={!canEdit} className="grid gap-4">
            <legend className="mb-1 font-semibold">Payment reminders</legend>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-primary mt-0.5 size-4"
                {...form.register("auto_reminders")}
              />
              <span>
                Remind customers automatically when an invoice is overdue
                <span className="text-muted-foreground block text-xs">
                  {whatsappApi
                    ? "Sent at 9 AM by WhatsApp, or email if there's no number. You can pause it on any invoice."
                    : "Sent at 9 AM by email to customers who have an email address. You can pause it on any invoice."}
                </span>
              </span>
            </label>
            {autoReminders && (
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  id="b-every"
                  label="Days between reminders"
                  error={errors.reminder_interval_days?.message}
                >
                  <Input
                    id="b-every"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={60}
                    {...form.register("reminder_interval_days")}
                  />
                </FormField>
                <FormField
                  id="b-max"
                  label="Most reminders per invoice"
                  error={errors.max_reminders?.message}
                >
                  <Input
                    id="b-max"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={10}
                    {...form.register("max_reminders")}
                  />
                </FormField>
              </div>
            )}
          </fieldset>
        </CardContent>
      </Card>
      {formError && <ErrorNote>{formError}</ErrorNote>}
      {canEdit ? (
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={isSubmitting || !isDirty}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
          {status && <span className="text-muted-foreground text-sm">{status}</span>}
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">Only owners and admins can change these.</p>
      )}
    </form>
  );
}
