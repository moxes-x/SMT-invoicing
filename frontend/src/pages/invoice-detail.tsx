import { zodResolver } from "@hookform/resolvers/zod";
import {
  Ban,
  Check,
  Copy,
  Download,
  ExternalLink,
  Mail,
  MessageCircle,
  Pencil,
  RefreshCw,
  Send,
  Trash2,
  Wallet,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";
import { z } from "zod";

import { ApiError } from "@/api/client";
import {
  useDeletePayment,
  useEmailInvoice,
  useInvoice,
  useInvoiceAction,
  useRecordPayment,
  useShareWhatsApp,
  type Invoice,
  type PaymentMethod,
} from "@/api/resources";
import { FormField } from "@/components/form-field";
import { MoneyInput } from "@/components/money-input";
import { ErrorNote } from "@/components/page";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { applyApiErrors } from "@/lib/apply-errors";
import { formatDate, formatDateTime, todayISO } from "@/lib/dates";
import { currencyPrefix, formatMoney, parseMoney, toMoneyInput } from "@/lib/money";

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "mtn_momo", label: "MTN MoMo" },
  { value: "airtel_money", label: "Airtel Money" },
  { value: "bank", label: "Bank transfer" },
  { value: "other", label: "Other" },
];

type DialogName = "payment" | "email" | "void" | "reissue" | null;

export function InvoiceDetailPage() {
  const id = Number(useParams().id);
  const { data: invoice, isLoading, error } = useInvoice(id);
  const [dialog, setDialog] = useState<DialogName>(null);

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (error || !invoice) return <ErrorNote>We couldn't find that invoice.</ErrorNote>;

  return (
    <div className="grid gap-4">
      <Summary invoice={invoice} />
      <Actions invoice={invoice} open={setDialog} />
      <Lines invoice={invoice} />
      {invoice.payments.length > 0 && <Payments invoice={invoice} />}
      <Timeline invoice={invoice} />

      <Dialog open={dialog === "payment"} onClose={() => setDialog(null)} title="Record payment">
        {dialog === "payment" && <PaymentForm invoice={invoice} onDone={() => setDialog(null)} />}
      </Dialog>
      <Dialog open={dialog === "email"} onClose={() => setDialog(null)} title="Send by email">
        {dialog === "email" && <EmailForm invoice={invoice} onDone={() => setDialog(null)} />}
      </Dialog>
      <Dialog
        open={dialog === "void" || dialog === "reissue"}
        onClose={() => setDialog(null)}
        title={dialog === "reissue" ? "Change this invoice" : "Void invoice"}
      >
        {(dialog === "void" || dialog === "reissue") && (
          <VoidForm
            invoice={invoice}
            reissue={dialog === "reissue"}
            onDone={() => setDialog(null)}
          />
        )}
      </Dialog>
    </div>
  );
}

function Summary({ invoice }: { invoice: Invoice }) {
  const c = invoice.currency;
  return (
    <Card className="gap-4">
      <CardContent className="grid gap-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-muted-foreground text-sm">{invoice.number}</p>
            <h1 className="truncate text-2xl font-semibold">{invoice.customer.name}</h1>
          </div>
          <StatusBadge status={invoice.display_status} />
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Fact label="Total" value={formatMoney(invoice.total, c)} />
          <Fact label="Paid" value={formatMoney(invoice.amount_paid, c)} />
          <Fact
            label="Balance"
            value={formatMoney(invoice.balance, c)}
            strong={invoice.status === "sent" && invoice.balance > 0}
          />
          <Fact label="Due" value={formatDate(invoice.due_date)} danger={invoice.is_overdue} />
        </div>
        {invoice.reissued_from && (
          <p className="text-muted-foreground text-sm">
            Replaces{" "}
            <Link className="text-primary underline" to={`/invoices/${invoice.reissued_from.id}`}>
              {invoice.reissued_from.number}
            </Link>
            .
          </p>
        )}
        {invoice.status === "void" && (
          <p className="bg-muted rounded-md p-3 text-sm">
            Voided {invoice.voided_at && formatDateTime(invoice.voided_at)}
            {invoice.void_reason && `: ${invoice.void_reason}`}.
            {invoice.reissued_as && (
              <>
                {" "}
                Replaced by{" "}
                <Link className="text-primary underline" to={`/invoices/${invoice.reissued_as.id}`}>
                  {invoice.reissued_as.number}
                </Link>
                .
              </>
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Fact({
  label,
  value,
  strong,
  danger,
}: {
  label: string;
  value: string;
  strong?: boolean;
  danger?: boolean;
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs tracking-wide uppercase">{label}</p>
      <p
        className={`font-semibold tabular-nums ${strong ? "text-primary" : ""} ${danger ? "text-destructive" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}

function Actions({ invoice, open }: { invoice: Invoice; open: (d: DialogName) => void }) {
  const whatsapp = useShareWhatsApp(invoice.id);
  const action = useInvoiceAction(invoice.id);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isDraft = invoice.status === "draft";
  const isSent = invoice.status === "sent";
  const canPay = isSent && invoice.balance > 0;

  const shareWhatsApp = async () => {
    setError(null);
    // Open the window synchronously so mobile browsers don't block it as a popup.
    const win = window.open("", "_blank");
    try {
      const { url } = await whatsapp.mutateAsync();
      if (win) win.location.href = url;
      else window.location.href = url;
    } catch (err) {
      win?.close();
      setError(err instanceof ApiError ? err.message : "Couldn't prepare the WhatsApp message.");
    }
  };

  const markSent = async () => {
    setError(null);
    try {
      await action.mutateAsync({ action: "send" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't mark as sent.");
    }
  };

  const copyLink = async () => {
    await navigator.clipboard?.writeText(invoice.public_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (invoice.status === "void") return null;

  return (
    <div className="grid gap-2">
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <Button
          onClick={shareWhatsApp}
          disabled={whatsapp.isPending}
          className="bg-[#1fa855] hover:bg-[#1fa855]/90"
        >
          <MessageCircle /> {isDraft ? "Send on WhatsApp" : "WhatsApp"}
        </Button>
        <Button variant={isDraft ? "outline" : "secondary"} onClick={() => open("email")}>
          <Mail /> Email
        </Button>
        {canPay && (
          <Button variant="default" onClick={() => open("payment")}>
            <Wallet /> Record payment
          </Button>
        )}
        {isDraft && (
          <Button asChild variant="outline">
            <Link to={`/invoices/${invoice.id}/edit`}>
              <Pencil /> Edit
            </Link>
          </Button>
        )}
        {isDraft && (
          <Button variant="outline" onClick={markSent} disabled={action.isPending}>
            <Send /> Mark as sent
          </Button>
        )}
        {isSent && (
          <Button variant="outline" onClick={copyLink}>
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy link"}
          </Button>
        )}
        <Button asChild variant="outline">
          <a href={invoice.public_url} target="_blank" rel="noreferrer">
            <ExternalLink /> {isDraft ? "Preview" : "Customer view"}
          </a>
        </Button>
        <Button asChild variant="outline">
          <a href={`/api/invoices/${invoice.id}/pdf/`}>
            <Download /> PDF
          </a>
        </Button>
        {isSent && (
          <Button variant="ghost" onClick={() => open("reissue")}>
            <RefreshCw /> Change
          </Button>
        )}
        {invoice.payments.length === 0 && (
          <Button variant="ghost" className="text-destructive" onClick={() => open("void")}>
            <Ban /> Void
          </Button>
        )}
      </div>
      {isDraft && (
        <p className="text-muted-foreground text-xs">
          Sending locks the invoice. To change it afterwards you void it and issue a corrected copy.
        </p>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Lines({ invoice }: { invoice: Invoice }) {
  const c = invoice.currency;
  return (
    <Section title="Items">
      <ul className="divide-y">
        {invoice.lines.map((l) => (
          <li key={l.id} className="flex justify-between gap-3 py-2 text-sm">
            <span className="min-w-0">
              <span className="block">{l.description}</span>
              <span className="text-muted-foreground text-xs">
                {Number(l.quantity)} × {formatMoney(l.unit_price, c)}
                {l.discount ? ` − ${formatMoney(l.discount, c)}` : ""}
              </span>
            </span>
            <span className="font-medium tabular-nums">{formatMoney(l.amount, c)}</span>
          </li>
        ))}
      </ul>
      <dl className="mt-3 grid gap-1 border-t pt-3 text-sm">
        {invoice.discount_total > 0 && (
          <>
            <Row label="Subtotal" value={formatMoney(invoice.subtotal, c)} />
            <Row label="Discount" value={`−${formatMoney(invoice.discount_total, c)}`} />
          </>
        )}
        <Row label="Total" value={formatMoney(invoice.total, c)} bold />
      </dl>
      {invoice.notes && (
        <p className="text-muted-foreground mt-3 text-sm whitespace-pre-line">{invoice.notes}</p>
      )}
    </Section>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={`flex justify-between ${bold ? "text-base font-semibold" : ""}`}>
      <dt className={bold ? "" : "text-muted-foreground"}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

function Payments({ invoice }: { invoice: Invoice }) {
  const remove = useDeletePayment();
  return (
    <Section title="Payments">
      <ul className="divide-y">
        {invoice.payments.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span>
              <span className="block font-medium">
                {formatMoney(p.amount, invoice.currency)} · {p.method_label}
              </span>
              <span className="text-muted-foreground text-xs">
                {formatDate(p.paid_on)}
                {p.reference && ` · Ref ${p.reference}`}
              </span>
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete payment"
              onClick={() => {
                if (window.confirm("Delete this payment? Use this to fix a mistake.")) {
                  remove.mutate(p.id);
                }
              }}
            >
              <Trash2 />
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Timeline({ invoice }: { invoice: Invoice }) {
  return (
    <Section title="Activity">
      <ol className="relative grid gap-4 border-l pl-5">
        {invoice.activity.map((a) => (
          <li key={a.id} className="text-sm">
            <span className="bg-primary absolute -left-[5px] mt-1.5 size-2.5 rounded-full" />
            <p className="font-medium">{a.message}</p>
            <p className="text-muted-foreground text-xs">
              {formatDateTime(a.created_at)}
              {a.actor_name && ` · ${a.actor_name}`}
            </p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

// ---- dialogs -------------------------------------------------------------------------------

const paymentSchema = z.object({
  amount: z.string().refine((v) => (parseMoney(v) ?? 0) > 0, "Enter an amount more than 0."),
  method: z.enum(["cash", "mtn_momo", "airtel_money", "bank", "other"]),
  paid_on: z.string().min(1),
  reference: z.string().max(100),
  note: z.string().max(300),
});

function PaymentForm({ invoice, onDone }: { invoice: Invoice; onDone: () => void }) {
  const record = useRecordPayment(invoice.id);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof paymentSchema>>({
    resolver: zodResolver(paymentSchema),
    defaultValues: {
      amount: toMoneyInput(invoice.balance),
      method: "mtn_momo",
      paid_on: todayISO(),
      reference: "",
      note: "",
    },
  });
  const { errors, isSubmitting } = form.formState;
  const onSubmit = form.handleSubmit(async ({ amount, ...v }) => {
    const value = parseMoney(amount)!;
    if (value > invoice.balance) {
      form.setError("amount", {
        message: `That is more than the balance of ${formatMoney(invoice.balance, invoice.currency)}.`,
      });
      return;
    }
    try {
      await record.mutateAsync({ ...v, amount: value });
      onDone();
    } catch (err) {
      setFormError(
        applyApiErrors(err, form.setError, ["amount", "method", "paid_on", "reference", "note"]),
      );
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <FormField id="p-amount" label="Amount" error={errors.amount?.message}>
        <MoneyInput
          id="p-amount"
          prefix={currencyPrefix(invoice.currency)}
          aria-invalid={!!errors.amount}
          {...form.register("amount")}
        />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField id="p-method" label="Method">
          <Select id="p-method" {...form.register("method")}>
            {METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField id="p-date" label="Date" error={errors.paid_on?.message}>
          <Input id="p-date" type="date" max={todayISO()} {...form.register("paid_on")} />
        </FormField>
      </div>
      <FormField id="p-ref" label="Reference (optional)" hint="e.g. the MoMo transaction ID">
        <Input id="p-ref" {...form.register("reference")} />
      </FormField>
      {formError && <ErrorNote>{formError}</ErrorNote>}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Saving…" : "Save payment"}
      </Button>
    </form>
  );
}

const emailSchema = z.object({
  to: z.email("Enter a valid email address."),
  message: z.string().max(1000),
});

function EmailForm({ invoice, onDone }: { invoice: Invoice; onDone: () => void }) {
  const email = useEmailInvoice(invoice.id);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof emailSchema>>({
    resolver: zodResolver(emailSchema),
    defaultValues: { to: invoice.customer.email ?? "", message: "" },
  });
  const { errors, isSubmitting } = form.formState;
  const onSubmit = form.handleSubmit(async (v) => {
    try {
      await email.mutateAsync(v);
      onDone();
    } catch (err) {
      setFormError(applyApiErrors(err, form.setError, ["to", "message"]));
    }
  });
  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <FormField id="e-to" label="To" error={errors.to?.message}>
        <Input id="e-to" type="email" aria-invalid={!!errors.to} {...form.register("to")} />
      </FormField>
      <FormField
        id="e-msg"
        label="Message (optional)"
        hint="We add a View invoice button and attach the PDF."
      >
        <Textarea id="e-msg" rows={3} {...form.register("message")} />
      </FormField>
      {invoice.status === "draft" && (
        <p className="text-muted-foreground text-xs">Sending will lock this invoice.</p>
      )}
      {formError && <ErrorNote>{formError}</ErrorNote>}
      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Sending…" : "Send email"}
      </Button>
    </form>
  );
}

function VoidForm({
  invoice,
  reissue,
  onDone,
}: {
  invoice: Invoice;
  reissue: boolean;
  onDone: () => void;
}) {
  const action = useInvoiceAction(invoice.id);
  const navigate = useNavigate();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setError(null);
    try {
      const result = await action.mutateAsync({ action: reissue ? "reissue" : "void", reason });
      onDone();
      if (reissue) navigate(`/invoices/${result.id}/edit`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  };
  return (
    <div className="grid gap-4">
      <p className="text-muted-foreground text-sm">
        {reissue
          ? `Sent invoices are locked, so ${invoice.number} will be voided and you'll edit a new copy with a new number. The customer's old link will show it was replaced.`
          : `${invoice.number} will be marked void. This can't be undone, but it stays in your records.`}
      </p>
      <FormField id="v-reason" label="Reason (optional)">
        <Input
          id="v-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Wrong price"
        />
      </FormField>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button
        variant={reissue ? "default" : "destructive"}
        onClick={submit}
        disabled={action.isPending}
      >
        {reissue ? "Void and create corrected copy" : "Void invoice"}
      </Button>
    </div>
  );
}
