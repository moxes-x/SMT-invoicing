import { Navigate, useNavigate, useParams, useSearchParams } from "react-router";

import { useMe } from "@/api/auth";
import { useInvoice, useSaveInvoice } from "@/api/resources";
import { DocumentEditor, EditorLoading } from "@/components/document-editor";
import { emptyValues, linesToValues, toLineRequests } from "@/lib/document-form";

export function InvoiceEditorPage() {
  const { id } = useParams();
  const invoiceId = id ? Number(id) : undefined;
  const { data: invoice, isLoading } = useInvoice(invoiceId);
  const { data: me } = useMe();
  const [params] = useSearchParams();
  const save = useSaveInvoice();
  const navigate = useNavigate();

  if (invoiceId && isLoading) return <EditorLoading />;
  if (invoice?.is_locked) return <Navigate to={`/invoices/${invoice.id}`} replace />;

  const base = emptyValues(
    params.get("customer") ?? "",
    me?.current_business?.default_currency ?? "ZMW",
  );
  const initial = invoice
    ? {
        ...base,
        customer_id: String(invoice.customer.id),
        currency: invoice.currency === "USD" ? ("USD" as const) : ("ZMW" as const),
        issue_date: invoice.issue_date ?? base.issue_date,
        due_date: invoice.due_date,
        notes: invoice.notes ?? "",
        lines: linesToValues(invoice.lines),
      }
    : base;

  return (
    <DocumentEditor
      mode="invoice"
      title={invoice ? `Edit ${invoice.number}` : "New invoice"}
      description="Saved as a draft. Nothing is sent until you choose to send it."
      initial={initial}
      cancelTo={invoice ? `/invoices/${invoice.id}` : "/invoices"}
      onSave={async (v) => {
        const saved = await save.mutateAsync({
          id: invoice?.id,
          customer_id: Number(v.customer_id),
          currency: v.currency,
          issue_date: v.issue_date,
          due_date: v.due_date,
          notes: v.notes,
          lines: toLineRequests(v.lines),
        });
        navigate(`/invoices/${saved.id}`);
      }}
    />
  );
}
