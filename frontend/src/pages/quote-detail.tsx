import {
  Check,
  Download,
  ExternalLink,
  FileOutput,
  MessageCircle,
  Pencil,
  Send,
  X,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useAccess } from "@/api/auth";
import { useAppConfig, useQuote, useQuoteAction, type Quote } from "@/api/resources";
import { Fact, LinesCard, Section, Timeline } from "@/components/document-parts";
import { FormField } from "@/components/form-field";
import { ErrorNote } from "@/components/page";
import { DeliveryList, SendForm } from "@/components/send-form";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { errorText, sendViaWhatsAppLink } from "@/lib/send";
import { formatDate, formatDateTime } from "@/lib/dates";
import { formatMoney } from "@/lib/money";

type DialogName = "send" | "convert" | null;

export function QuoteDetailPage() {
  const id = Number(useParams().id);
  const { data: quote, isLoading, error } = useQuote(id);
  const { data: config } = useAppConfig();
  const actions = useQuoteAction(id);
  const [dialog, setDialog] = useState<DialogName>(null);

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (error || !quote) return <ErrorNote>We couldn't find that quote.</ErrorNote>;

  return (
    <div className="grid gap-4">
      <Summary quote={quote} />
      <Actions quote={quote} open={setDialog} />
      <LinesCard doc={quote} />
      {quote.deliveries.length > 0 && (
        <Section title="Sending">
          <DeliveryList deliveries={quote.deliveries} />
        </Section>
      )}
      <Timeline activity={quote.activity} />

      <Dialog open={dialog === "send"} onClose={() => setDialog(null)} title="Send quote">
        {dialog === "send" && (
          <SendForm
            customer={quote.customer}
            whatsappApi={!!config?.whatsapp_api}
            send={actions.send.mutateAsync}
            onDone={() => setDialog(null)}
          />
        )}
      </Dialog>
      <Dialog
        open={dialog === "convert"}
        onClose={() => setDialog(null)}
        title="Turn into an invoice"
      >
        {dialog === "convert" && <ConvertForm quote={quote} />}
      </Dialog>
    </div>
  );
}

function Summary({ quote }: { quote: Quote }) {
  const expired = quote.display_status === "expired";
  return (
    <Card className="gap-4">
      <CardContent className="grid gap-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-muted-foreground text-sm">{quote.number}</p>
            <h1 className="truncate text-2xl font-semibold">{quote.customer.name}</h1>
          </div>
          <StatusBadge status={quote.display_status} />
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <Fact label="Total" value={formatMoney(quote.total, quote.currency ?? "ZMW")} strong />
          <Fact label="Date" value={formatDate(quote.issue_date)} />
          <Fact label="Valid until" value={formatDate(quote.valid_until)} danger={expired} />
        </div>
        {quote.responded_at && (quote.status === "accepted" || quote.status === "declined") && (
          <p className="bg-muted rounded-md p-3 text-sm">
            {quote.status === "accepted" ? "Accepted" : "Declined"}{" "}
            {formatDateTime(quote.responded_at)}.
          </p>
        )}
        {quote.converted_invoice && (
          <p className="bg-muted rounded-md p-3 text-sm">
            Invoiced as{" "}
            <Link className="text-primary underline" to={`/invoices/${quote.converted_invoice.id}`}>
              {quote.converted_invoice.number}
            </Link>
            .
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function Actions({ quote, open }: { quote: Quote; open: (d: DialogName) => void }) {
  const { send, respond } = useQuoteAction(quote.id);
  const { canWrite } = useAccess();
  const [error, setError] = useState<string | null>(null);
  const isDraft = quote.status === "draft";
  const isSent = quote.status === "sent";
  const canConvert = quote.status !== "converted" && quote.status !== "declined";

  const run = async (fn: () => Promise<unknown>, fallback: string) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(errorText(err, fallback));
    }
  };

  return (
    <div className="grid gap-2">
      <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        {canWrite && (isDraft || isSent) && (
          <Button
            onClick={() =>
              run(() => sendViaWhatsAppLink(send.mutateAsync), "Couldn't prepare the message.")
            }
            disabled={send.isPending}
            className="bg-[#1fa855] hover:bg-[#1fa855]/90"
          >
            <MessageCircle /> {isDraft ? "Send on WhatsApp" : "WhatsApp"}
          </Button>
        )}
        {canWrite && (isDraft || isSent) && (
          <Button variant="outline" onClick={() => open("send")}>
            <Send /> {isDraft ? "Other ways to send" : "Send again"}
          </Button>
        )}
        {canWrite && canConvert && (
          <Button
            variant={quote.status === "accepted" ? "default" : "outline"}
            onClick={() => open("convert")}
          >
            <FileOutput /> Make invoice
          </Button>
        )}
        {canWrite && quote.is_editable && (
          <Button asChild variant="outline">
            <Link to={`/quotes/${quote.id}/edit`}>
              <Pencil /> Edit
            </Link>
          </Button>
        )}
        {canWrite && isSent && quote.display_status !== "expired" && (
          <>
            <Button
              variant="outline"
              onClick={() => run(() => respond.mutateAsync(true), "Couldn't save.")}
              disabled={respond.isPending}
            >
              <Check /> Mark accepted
            </Button>
            <Button
              variant="ghost"
              onClick={() => run(() => respond.mutateAsync(false), "Couldn't save.")}
              disabled={respond.isPending}
            >
              <X /> Mark declined
            </Button>
          </>
        )}
        <Button asChild variant="outline">
          <a href={quote.public_url} target="_blank" rel="noreferrer">
            <ExternalLink /> {isDraft ? "Preview" : "Customer view"}
          </a>
        </Button>
        <Button asChild variant="outline">
          <a href={`/api/quotes/${quote.id}/pdf/`}>
            <Download /> PDF
          </a>
        </Button>
      </div>
      {isSent && (
        <p className="text-muted-foreground text-xs">
          Your customer can accept or decline from the link. You can also record their answer here.
        </p>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
    </div>
  );
}

function ConvertForm({ quote }: { quote: Quote }) {
  const { convert } = useQuoteAction(quote.id);
  const navigate = useNavigate();
  const [days, setDays] = useState("14");
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setError(null);
    const n = Number(days);
    if (!Number.isInteger(n) || n < 0 || n > 120) {
      setError("Enter between 0 and 120 days.");
      return;
    }
    try {
      const invoice = await convert.mutateAsync(n);
      navigate(`/invoices/${invoice.id}`);
    } catch (err) {
      setError(errorText(err, "Couldn't create the invoice."));
    }
  };
  return (
    <div className="grid gap-4">
      <p className="text-muted-foreground text-sm">
        We'll create a draft invoice for {quote.customer.name} with the same items. You can check it
        before sending.
      </p>
      <FormField id="c-days" label="Payment due in (days)">
        <Input
          id="c-days"
          type="number"
          inputMode="numeric"
          min={0}
          max={120}
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
      </FormField>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button onClick={submit} disabled={convert.isPending}>
        {convert.isPending ? "Creating…" : "Create draft invoice"}
      </Button>
    </div>
  );
}
