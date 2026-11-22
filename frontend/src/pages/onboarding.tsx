import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";

import { useCreateBusiness } from "@/api/auth";
import { AuthLayout } from "@/components/auth-layout";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { applyApiErrors } from "@/lib/apply-errors";
import { cn } from "@/lib/utils";

const schema = z.object({
  name: z.string().min(1, "Enter your business name.").max(200),
  phone: z.string().optional(),
  email: z.union([z.email("Enter a valid email address."), z.literal("")]).optional(),
  tpin: z
    .string()
    .regex(/^(\d{10})?$/, "TPIN is 10 digits (or leave it blank).")
    .optional(),
  vat_registered: z.enum(["yes", "no"], { error: "Choose yes or no." }),
});
type Values = z.infer<typeof schema>;

export function OnboardingPage() {
  const navigate = useNavigate();
  const create = useCreateBusiness();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const { errors, isSubmitting } = form.formState;
  const vat = useWatch({ control: form.control, name: "vat_registered" });

  const onSubmit = form.handleSubmit(async ({ vat_registered, ...rest }) => {
    setFormError(null);
    try {
      await create.mutateAsync({ ...rest, vat_registered: vat_registered === "yes" });
      navigate("/");
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, ["name", "phone", "email", "tpin"]));
    }
  });

  return (
    <AuthLayout>
      <Card>
        <CardHeader>
          <CardTitle>Tell us about your business</CardTitle>
          <CardDescription>This is what your customers see on every invoice.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid gap-4" noValidate>
            <FormField id="name" label="Business name" error={errors.name?.message}>
              <Input id="name" aria-invalid={!!errors.name} {...form.register("name")} />
            </FormField>
            <FormField
              id="phone"
              label="Phone (optional)"
              error={errors.phone?.message}
              hint="e.g. 097 123 4567"
            >
              <Input
                id="phone"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                {...form.register("phone")}
              />
            </FormField>
            <FormField id="email" label="Business email (optional)" error={errors.email?.message}>
              <Input id="email" type="email" {...form.register("email")} />
            </FormField>
            <FormField id="tpin" label="TPIN (optional)" error={errors.tpin?.message}>
              <Input id="tpin" inputMode="numeric" maxLength={10} {...form.register("tpin")} />
            </FormField>

            <fieldset className="grid gap-2">
              <legend className="mb-2 text-sm font-medium">Are you VAT-registered?</legend>
              <div className="grid grid-cols-2 gap-2">
                {(["no", "yes"] as const).map((v) => (
                  <label
                    key={v}
                    className={cn(
                      "flex h-11 cursor-pointer items-center justify-center rounded-md border text-sm font-medium",
                      vat === v && "border-primary bg-accent text-accent-foreground",
                    )}
                  >
                    <input
                      type="radio"
                      value={v}
                      className="sr-only"
                      {...form.register("vat_registered")}
                    />
                    {v === "yes" ? "Yes" : "No"}
                  </label>
                ))}
              </div>
              {errors.vat_registered && (
                <p role="alert" className="text-destructive text-sm">
                  {errors.vat_registered.message}
                </p>
              )}
            </fieldset>

            {vat === "yes" && (
              <div className="border-warning/60 bg-warning/10 flex gap-2 rounded-md border p-3 text-sm">
                <Info className="mt-0.5 size-4 shrink-0" />
                <p>
                  VAT-registered businesses must issue tax invoices through{" "}
                  <strong>ZRA Smart Invoice</strong>. Documents from this app are plain invoices,
                  not tax invoices, but you can still use it to track who has paid.
                </p>
              </div>
            )}

            {formError && (
              <p role="alert" className="text-destructive text-sm">
                {formError}
              </p>
            )}
            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? "Saving…" : "Continue"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </AuthLayout>
  );
}
