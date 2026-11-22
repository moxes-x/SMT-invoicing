import { zodResolver } from "@hookform/resolvers/zod";
import { Mail, MessageCircle, Send } from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import type { Delivery, SendChannel } from "@/api/resources";
import { FormField } from "@/components/form-field";
import { ErrorNote } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDateTime } from "@/lib/dates";
import { sendViaWhatsAppLink, errorText, type Send as SendFn } from "@/lib/send";
import { cn } from "@/lib/utils";

const CHANNELS: {
  value: SendChannel;
  label: string;
  hint: string;
  icon: typeof Mail;
}[] = [
  {
    value: "whatsapp_link",
    label: "WhatsApp from my phone",
    hint: "Opens WhatsApp with the message ready. You press send.",
    icon: MessageCircle,
  },
  {
    value: "whatsapp",
    label: "WhatsApp, sent for me",
    hint: "Sent from your business number with the PDF attached. You'll see when it's read.",
    icon: Send,
  },
  {
    value: "email",
    label: "Email",
    hint: "With a View button and the PDF attached.",
    icon: Mail,
  },
];

const schema = z
  .object({
    channel: z.enum(["whatsapp_link", "whatsapp", "email"]),
    to: z.string(),
    message: z.string().max(1000),
  })
  .superRefine((v, ctx) => {
    if (v.channel === "email" && !z.email().safeParse(v.to).success) {
      ctx.addIssue({ code: "custom", path: ["to"], message: "Enter a valid email address." });
    }
  });

/** Pick a channel and send an invoice, quote or reminder. */
export function SendForm({
  customer,
  whatsappApi,
  send,
  onDone,
  note,
  submitLabel = "Send",
}: {
  customer: { phone?: string; email?: string };
  whatsappApi: boolean;
  send: SendFn;
  onDone: () => void;
  note?: string;
  submitLabel?: string;
}) {
  const channels = CHANNELS.filter((c) => c.value !== "whatsapp" || whatsappApi);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: {
      channel: customer.phone ? (whatsappApi ? "whatsapp" : "whatsapp_link") : "email",
      to: customer.email ?? "",
      message: "",
    },
  });
  const channel = useWatch({ control: form.control, name: "channel" });
  const { errors, isSubmitting } = form.formState;
  const needsPhone = channel !== "email" && !customer.phone;

  const onSubmit = form.handleSubmit(async (v) => {
    setFormError(null);
    try {
      if (v.channel === "whatsapp_link") await sendViaWhatsAppLink(send);
      else if (v.channel === "whatsapp") await send({ channel: "whatsapp" });
      else await send({ channel: "email", to: v.to, message: v.message });
      onDone();
    } catch (err) {
      setFormError(errorText(err, "Couldn't send. Please try again."));
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-medium">Send by</legend>
        {channels.map(({ value, label, hint, icon: Icon }) => (
          <label
            key={value}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm",
              channel === value && "border-primary bg-accent/60",
            )}
          >
            <input type="radio" value={value} className="sr-only" {...form.register("channel")} />
            <Icon className="text-primary mt-0.5 size-5 shrink-0" />
            <span>
              <span className="block font-medium">{label}</span>
              <span className="text-muted-foreground text-xs">{hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {channel === "email" && (
        <>
          <FormField id="s-to" label="To" error={errors.to?.message}>
            <Input id="s-to" type="email" aria-invalid={!!errors.to} {...form.register("to")} />
          </FormField>
          <FormField id="s-msg" label="Message (optional)">
            <Textarea id="s-msg" rows={3} {...form.register("message")} />
          </FormField>
        </>
      )}
      {needsPhone && (
        <ErrorNote>This customer has no WhatsApp number. Add one on the Customers page.</ErrorNote>
      )}
      {note && <p className="text-muted-foreground text-xs">{note}</p>}
      {formError && <ErrorNote>{formError}</ErrorNote>}
      <Button type="submit" disabled={isSubmitting || needsPhone}>
        {isSubmitting ? "Sending…" : submitLabel}
      </Button>
    </form>
  );
}

const DELIVERY_STATUS: Record<
  Delivery["status"],
  { label: string; tone: "neutral" | "info" | "success" | "danger" | "brand" }
> = {
  queued: { label: "Sending", tone: "neutral" },
  shared: { label: "Opened WhatsApp", tone: "neutral" },
  sent: { label: "Sent", tone: "info" },
  delivered: { label: "Delivered", tone: "brand" },
  read: { label: "Read", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

const KIND_LABEL: Record<Delivery["kind"], string> = {
  invoice: "Invoice",
  reminder: "Reminder",
  quote: "Quote",
};

export function DeliveryList({ deliveries }: { deliveries: Delivery[] }) {
  return (
    <ul className="divide-y">
      {deliveries.map((d) => {
        const s = DELIVERY_STATUS[d.status];
        return (
          <li key={d.id} className="flex items-start justify-between gap-3 py-2 text-sm">
            <span className="min-w-0">
              <span className="block font-medium">
                {KIND_LABEL[d.kind]} by {d.channel === "email" ? "email" : "WhatsApp"}
                {d.automatic && " (automatic)"}
              </span>
              <span className="text-muted-foreground block truncate text-xs">
                {d.recipient} · {formatDateTime(d.created_at)}
              </span>
              {d.status === "failed" && d.error && (
                <span className="text-destructive block text-xs">{d.error}</span>
              )}
            </span>
            <Badge tone={s.tone}>{s.label}</Badge>
          </li>
        );
      })}
    </ul>
  );
}
