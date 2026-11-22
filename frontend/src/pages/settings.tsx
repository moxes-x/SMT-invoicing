import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useMe } from "@/api/auth";
import { useUpdateBusiness } from "@/api/resources";
import { FormField } from "@/components/form-field";
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
});
type Values = z.infer<typeof schema>;
const FIELDS = ["name", "phone", "email", "address", "tpin", "payment_details"] as const;

export function SettingsPage() {
  const { data: me } = useMe();
  const business = me?.current_business;
  if (!business) return null;
  return <BusinessForm key={business.id} />;
}

function BusinessForm() {
  const { data: me } = useMe();
  const business = me!.current_business!;
  const update = useUpdateBusiness(business.id);
  const [status, setStatus] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const canEdit = business.role === "owner" || business.role === "admin";
  const form = useForm<Values>({
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
    },
  });
  const { errors, isSubmitting, isDirty } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setStatus(null);
    setFormError(null);
    try {
      const saved = await update.mutateAsync(values);
      form.reset({ ...values, phone: saved.phone ?? "" });
      setStatus("Saved.");
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, FIELDS));
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <PageHeader title="Business settings" description="Shown on every invoice you send." />
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
