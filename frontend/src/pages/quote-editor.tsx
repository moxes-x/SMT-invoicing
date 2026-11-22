import { Navigate, useNavigate, useParams, useSearchParams } from "react-router";

import { useMe } from "@/api/auth";
import { useQuote, useSaveQuote } from "@/api/resources";
import { DocumentEditor, EditorLoading } from "@/components/document-editor";
import { emptyValues, linesToValues, toLineRequests } from "@/lib/document-form";

export function QuoteEditorPage() {
  const { id } = useParams();
  const quoteId = id ? Number(id) : undefined;
  const { data: quote, isLoading } = useQuote(quoteId);
  const { data: me } = useMe();
  const [params] = useSearchParams();
  const save = useSaveQuote();
  const navigate = useNavigate();

  if (quoteId && isLoading) return <EditorLoading />;
  if (quote && !quote.is_editable) return <Navigate to={`/quotes/${quote.id}`} replace />;

  const base = emptyValues(
    params.get("customer") ?? "",
    me?.current_business?.default_currency ?? "ZMW",
    "quote",
  );
  const initial = quote
    ? {
        ...base,
        customer_id: String(quote.customer.id),
        currency: quote.currency === "USD" ? ("USD" as const) : ("ZMW" as const),
        issue_date: quote.issue_date ?? base.issue_date,
        due_date: quote.valid_until,
        notes: quote.notes ?? "",
        lines: linesToValues(quote.lines),
      }
    : base;

  return (
    <DocumentEditor
      mode="quote"
      title={quote ? `Edit ${quote.number}` : "New quote"}
      description="Your customer can accept or decline it from the link you send."
      initial={initial}
      cancelTo={quote ? `/quotes/${quote.id}` : "/quotes"}
      submitLabel="Save quote"
      onSave={async (v) => {
        const saved = await save.mutateAsync({
          id: quote?.id,
          customer_id: Number(v.customer_id),
          currency: v.currency,
          issue_date: v.issue_date,
          valid_until: v.due_date,
          notes: v.notes,
          lines: toLineRequests(v.lines),
        });
        navigate(`/quotes/${saved.id}`);
      }}
    />
  );
}
