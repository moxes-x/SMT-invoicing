import { zodResolver } from "@hookform/resolvers/zod";
import {
  Ban,
  BellOff,
  BellRing,
  Check,
  Copy,
  Download,
  ExternalLink,
  MessageCircle,
  Pencil,
  ReceiptText,
  RefreshCw,
  Send,
  Trash2,
  Wallet,
} from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";
import { z } from "zod";

import { useAccess, useMe } from "@/api/auth";
import {
  useAppConfig,
  useDeletePayment,
  useInvoice,
  useInvoiceAction,
  usePauseReminders,
  useRecordPayment,
  useSendInvoice,
  useSetExchangeRate,
  type Invoice,
  type PaymentMethod,
} from "@/api/resources";
import { Fact, LinesCard, Section, Timeline } from "@/components/document-parts";
import { FormField } from "@/components/form-field";
import { MoneyInput } from "@/components/money-input";
import { ErrorNote } from "@/components/page";
import { DeliveryList, SendForm } from "@/components/send-form";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { applyApiErrors } from "@/lib/apply-errors";
import { errorText, sendViaWhatsAppLink } from "@/lib/send";
import { formatDate, formatDateTime, todayISO } from "@/lib/dates";
import { isRate, rateInput } from "@/lib/document-form";
import { translate, type Lang } from "@/i18n";
import { currencyPrefix, formatMoney, parseMoney, toMoneyInput } from "@/lib/money";

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "mtn_momo", label: "MTN MoMo" },
  { value: "airtel_money", label: "Airtel Money" },
  { value: "zamtel_kwacha", label: "Zamtel Kwacha" },
  { value: "card", label: "Card" },
  { value: "bank", label: "Bank transfer" },
  { value: "other", label: "Other" },
];

type DialogName = "payment" | "send" | "remind" | "void" | "reissue" | null;

export function InvoiceDetailPage() {
  const id = Number(useParams().id);
  const { data: invoice, isLoading, error } = useInvoice(id);
  const [dialog, setDialog] = useState<DialogName>(null);
  const { data: config } = useAppConfig();
  const deliver = useSendInvoice(id, "deliver");
  const remind = useSendInvoice(id, "remind");
  const whatsappApi = !!config?.whatsapp_api;

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (error || !invoice) return <ErrorNote>We couldn't find that invoice.</ErrorNote>;

  return (
    <div className="grid gap-4">
      <Summary invoice={invoice} />
      <Actions invoice={invoice} open={setDialog} />
      <LinesCard doc={invoice} />
      {invoice.payments.length > 0 && <Payments invoice={invoice} />}
      {(invoice.deliveries.length > 0 || invoice.status === "sent") && (
        <Sending invoice={invoice} />
      )}
      <Timeline activity={invoice.activity} />

      <Dialog open={dialog === "payment"} onClose={() => setDialog(null)} title="Record payment">
        {dialog === "payment" && <PaymentForm invoice={invoice} onDone={() => setDialog(null)} />}
      </Dialog>
      <Dialog open={dialog === "send"} onClose={() => setDialog(null)} title="Send invoice">
        {dialog === "send" && (
          <SendForm
            customer={invoice.customer}
            whatsappApi={whatsappApi}
            send={deliver.mutateAsync}
            onDone={() => setDialog(null)}
            note={invoice.status === "draft" ? "Sending will lock this invoice." : undefined}
          />
        )}
      </Dialog>
      <Dialog open={dialog === "remind"} onClose={() => setDialog(null)} title="Send a reminder">
        {dialog === "remind" && (
          <SendForm
            customer={invoice.customer}
            whatsappApi={whatsappApi}
            send={remind.mutateAsync}
            onDone={() => setDialog(null)}
            note={`Reminds ${invoice.customer.name} of the balance of ${formatMoney(invoice.balance, invoice.currency)} with a link to the invoice.`}
            submitLabel="Send reminder"
          />
        )}
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
        {c !== "ZMW" && invoice.status !== "void" && <ExchangeRate invoice={invoice} />}
        <ZraReceipts invoice={invoice} />
        {(invoice.from_quote || invoice.recurring_id) && (
          <p className="text-muted-foreground text-sm">
            {invoice.from_quote && (
              <>
                From quote{" "}
                <Link className="text-primary underline" to={`/quotes/${invoice.from_quote.id}`}>
                  {invoice.from_quote.number}
                </Link>
                .{" "}
              </>
            )}
            {invoice.recurring_id && (
              <Link
                className="text-primary underline"
                to={`/recurring/${invoice.recurring_id}/edit`}
              >
                Made by a repeating invoice
              </Link>
            )}
          </p>
        )}
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

function Actions({ invoice, open }: { invoice: Invoice; open: (d: DialogName) => void }) {
  const { data: config } = useAppConfig();
  const deliver = useSendInvoice(invoice.id, "deliver");
  const { canWrite, canManage } = useAccess();
  const action = useInvoiceAction(invoice.id);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isDraft = invoice.status === "draft";
  const isSent = invoice.status === "sent";
  const canPay = isSent && invoice.balance > 0;

  const shareWhatsApp = async () => {
    setError(null);
    try {
      await sendViaWhatsAppLink(deliver.mutateAsync);
    } catch (err) {
      setError(errorText(err, "Couldn't prepare the WhatsApp message."));
    }
  };

  const markSent = async () => {
    setError(null);
    try {
      await action.mutateAsync({ action: "send" });
    } catch (err) {
      setError(errorText(err, "Couldn't mark as sent."));
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
        {canWrite && (
          <Button
            onClick={shareWhatsApp}
            disabled={deliver.isPending}
            className="bg-[#1fa855] hover:bg-[#1fa855]/90"
          >
            <MessageCircle /> {isDraft ? "Send on WhatsApp" : "WhatsApp"}
          </Button>
        )}
        {canWrite && (
          <Button variant={isDraft ? "outline" : "secondary"} onClick={() => open("send")}>
            <Send /> {isDraft ? "Other ways to send" : "Send again"}
          </Button>
        )}
        {canWrite && canPay && (
          <Button variant="default" onClick={() => open("payment")}>
            <Wallet /> Record payment
          </Button>
        )}
        {canWrite && canPay && (
          <Button variant="outline" onClick={() => open("remind")}>
            <BellRing /> Send reminder
          </Button>
        )}
        {canWrite && isDraft && (
          <Button asChild variant="outline">
            <Link to={`/invoices/${invoice.id}/edit`}>
              <Pencil /> Edit
            </Link>
          </Button>
        )}
        {canWrite && isDraft && (
          <Button variant="outline" onClick={markSent} disabled={action.isPending}>
            <Check /> Mark as sent
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
        {canManage && isSent && (
          <Button variant="ghost" onClick={() => open("reissue")}>
            <RefreshCw /> Change
          </Button>
        )}
        {canManage && invoice.payments.length === 0 && (
          <Button variant="ghost" className="text-destructive" onClick={() => open("void")}>
            <Ban /> Void
          </Button>
        )}
      </div>
      {canPay && config?.online_payments && invoice.currency === "ZMW" && (
        <p className="text-muted-foreground text-xs">
          Your customer can pay this online from the invoice link (Pay now). It's marked paid by
          itself when the money arrives.
        </p>
      )}
      {isDraft && (
        <p className="text-muted-foreground text-xs">
          Sending locks the invoice. To change it afterwards you void it and issue a corrected copy.
        </p>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
    </div>
  );
}

/** Kwacha rate of a foreign-currency invoice: shown, or added later for the Kwacha reports. */
/** The ZRA receipts for a tax invoice: the sale, and the credit note if it was voided. */
function ZraReceipts({ invoice }: { invoice: Invoice }) {
  const receipts = invoice.fiscal_receipts ?? [];
  if (!receipts.length) return null;
  return (
    <section aria-label="ZRA Smart Invoice" className="bg-muted grid gap-2 rounded-md p-3 text-sm">
      <p className="font-medium">Tax invoice, signed by ZRA</p>
      {receipts.map((r) => (
        <dl key={r.id} className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          <dt className="text-muted-foreground">
            {r.kind === "credit" ? `Credit note ${r.document_number}` : "ZRA receipt"}
          </dt>
          <dd>{r.receipt_no || "–"}</dd>
          <dt className="text-muted-foreground">SDC ID</dt>
          <dd className="[overflow-wrap:anywhere]">{r.sdc_id || "–"}</dd>
          {r.kind === "sale" && (
            <>
              <dt className="text-muted-foreground">VAT</dt>
              <dd>{formatMoney(Math.round(Number(r.tax_total) * 100), invoice.currency)}</dd>
            </>
          )}
          {r.qr_url && (
            <>
              <dt className="text-muted-foreground">Check</dt>
              <dd>
                <a
                  className="text-primary underline"
                  href={r.qr_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  On the ZRA portal
                </a>
              </dd>
            </>
          )}
        </dl>
      ))}
    </section>
  );
}

function ExchangeRate({ invoice }: { invoice: Invoice }) {
  const { canWrite } = useAccess();
  const set = useSetExchangeRate(invoice.id);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(rateInput(invoice.exchange_rate));
  const [error, setError] = useState<string | null>(null);
  const rate = invoice.exchange_rate ? Number(invoice.exchange_rate) : null;

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isRate(value)) return setError("Kwacha for one unit, like 26.85.");
    setError(null);
    try {
      await set.mutateAsync(value.trim().replace(/,/g, ""));
      setEditing(false);
    } catch (err) {
      setError(errorText(err, "Couldn't save the rate."));
    }
  };

  if (editing) {
    return (
      <form onSubmit={save} className="grid gap-2" noValidate>
        <FormField
          id="rate"
          label={`Kwacha per ${currencyPrefix(invoice.currency)}1`}
          error={error ?? undefined}
        >
          <div className="flex gap-2">
            <Input
              id="rate"
              inputMode="decimal"
              placeholder="e.g. 26.85"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              aria-invalid={!!error}
            />
            <Button type="submit" disabled={set.isPending}>
              Save
            </Button>
          </div>
        </FormField>
      </form>
    );
  }
  return (
    <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-sm">
      {rate ? (
        <span>
          {formatMoney(Math.round(invoice.total * rate), "ZMW")} at K{rate} ={" "}
          {currencyPrefix(invoice.currency)}1
        </span>
      ) : (
        <span>No exchange rate yet, so Kwacha reports leave this invoice out.</span>
      )}
      {canWrite && !invoice.fiscal_receipts?.length && (
        <Button variant="link" size="sm" className="h-auto p-0" onClick={() => setEditing(true)}>
          {rate ? "Change rate" : "Add rate"}
        </Button>
      )}
    </p>
  );
}

/** In the customer's language (set on the customer), not the app's. */
function receiptText(invoice: Invoice, p: Invoice["payments"][number]): string {
  const first = invoice.customer.name?.split(" ")[0];
  const lang = invoice.customer.language === "bem" || invoice.customer.language === "ny";
  return translate(lang ? (invoice.customer.language as Lang) : "en", "receipt.message", {
    commaName: first ? `, ${first}` : "",
    receipt: p.receipt_number ?? "",
    amount: formatMoney(p.amount, invoice.currency),
    number: invoice.number,
    url: p.receipt_url,
  });
}

function Payments({ invoice }: { invoice: Invoice }) {
  const remove = useDeletePayment();
  const { canManage } = useAccess();
  const phone = invoice.customer.phone?.replace("+", "") ?? "";
  return (
    <Section title="Payments">
      <ul className="divide-y">
        {invoice.payments.map((p) => (
          <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2 font-medium">
                {formatMoney(p.amount, invoice.currency)} · {p.method_label}
                {p.source === "online" && <Badge tone="success">Paid online</Badge>}
              </span>
              <span className="text-muted-foreground block text-xs">
                {formatDate(p.paid_on)}
                {p.receipt_number && ` · ${p.receipt_number}`}
                {p.reference && ` · Ref ${p.reference}`}
              </span>
            </span>
            <span className="flex shrink-0 items-center">
              <Button asChild variant="ghost" size="icon" aria-label="Open receipt">
                <a href={p.receipt_url} target="_blank" rel="noreferrer">
                  <ReceiptText />
                </a>
              </Button>
              <Button asChild variant="ghost" size="icon" aria-label="Send receipt on WhatsApp">
                <a
                  href={`https://wa.me/${phone}?text=${encodeURIComponent(receiptText(invoice, p))}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <MessageCircle />
                </a>
              </Button>
              {canManage && p.source !== "online" && (
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
              )}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Sending({ invoice }: { invoice: Invoice }) {
  const { data: me } = useMe();
  const pause = usePauseReminders(invoice.id);
  const { canWrite } = useAccess();
  const business = me?.current_business;
  const chasing = invoice.status === "sent" && invoice.balance > 0;
  const auto = canWrite && !!business?.auto_reminders && chasing;
  return (
    <Section
      title="Sending"
      action={
        auto && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => pause.mutate(!invoice.reminders_paused)}
            disabled={pause.isPending}
          >
            {invoice.reminders_paused ? <BellRing /> : <BellOff />}
            {invoice.reminders_paused ? "Resume reminders" : "Pause reminders"}
          </Button>
        )
      }
    >
      {chasing && (
        <p className="text-muted-foreground mb-2 text-sm">
          {!business?.auto_reminders
            ? "Automatic reminders are off. Turn them on in Settings."
            : invoice.reminders_paused
              ? "Automatic reminders are paused for this invoice."
              : `Automatic reminders are on: every ${business.reminder_interval_days} days once overdue, up to ${business.max_reminders}.`}{" "}
          {invoice.reminder_count > 0 &&
            `${invoice.reminder_count} reminder${invoice.reminder_count === 1 ? "" : "s"} sent so far.`}
        </p>
      )}
      {invoice.deliveries.length > 0 ? (
        <DeliveryList deliveries={invoice.deliveries} />
      ) : (
        <p className="text-muted-foreground text-sm">Not sent through the app yet.</p>
      )}
    </Section>
  );
}

// ---- dialogs -------------------------------------------------------------------------------

const paymentSchema = z.object({
  amount: z.string().refine((v) => (parseMoney(v) ?? 0) > 0, "Enter an amount more than 0."),
  method: z.enum(["cash", "mtn_momo", "airtel_money", "zamtel_kwacha", "card", "bank", "other"]),
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
      setError(errorText(err, "Something went wrong."));
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
