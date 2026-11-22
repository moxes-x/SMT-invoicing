import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";

import { useSignup } from "@/api/auth";
import { AuthLayout } from "@/components/auth-layout";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { applyApiErrors } from "@/lib/apply-errors";

const schema = z.object({
  full_name: z.string().max(150).optional(),
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Use at least 8 characters."),
});
type Values = z.infer<typeof schema>;

export function SignupPage() {
  const navigate = useNavigate();
  const signup = useSignup();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    setFormError(null);
    try {
      await signup.mutateAsync(values);
      navigate("/onboarding");
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, ["full_name", "email", "password"]));
    }
  });

  return (
    <AuthLayout>
      <Card>
        <CardHeader>
          <CardTitle>Create your account</CardTitle>
          <CardDescription>Free for up to 10 invoices a month.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="grid gap-4" noValidate>
            <FormField id="full_name" label="Your name" error={errors.full_name?.message}>
              <Input id="full_name" autoComplete="name" {...form.register("full_name")} />
            </FormField>
            <FormField id="email" label="Email" error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                aria-invalid={!!errors.email}
                {...form.register("email")}
              />
            </FormField>
            <FormField id="password" label="Password" error={errors.password?.message}>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                aria-invalid={!!errors.password}
                {...form.register("password")}
              />
            </FormField>
            {formError && (
              <p role="alert" className="text-destructive text-sm">
                {formError}
              </p>
            )}
            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? "Creating account…" : "Create account"}
            </Button>
            <p className="text-muted-foreground text-center text-sm">
              Already have an account?{" "}
              <Link
                to="/login"
                className="text-primary font-medium underline-offset-4 hover:underline"
              >
                Log in
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </AuthLayout>
  );
}
