import { FilePlus2, FileSignature, Search } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { useAccess } from "@/api/auth";
import { useQuotes } from "@/api/resources";
import { EmptyState, PageHeader } from "@/components/page";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDate } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

const FILTERS = [
  { value: "", label: "All" },
  { value: "open", label: "Open" },
  { value: "accepted", label: "Accepted" },
  { value: "draft", label: "Drafts" },
  { value: "expired", label: "Expired" },
  { value: "declined", label: "Declined" },
  { value: "converted", label: "Invoiced" },
];

export function QuotesPage() {
  const { canWrite } = useAccess();
  const t = useT();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const search = params.get("search") ?? "";
  const { data, isLoading } = useQuotes({ status, search });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="grid gap-4">
      <PageHeader
        title={t("nav.quotes")}
        description="Send a price first. When the customer accepts, turn it into an invoice."
        actions={
          canWrite && (
            <Button asChild>
              <Link to="/quotes/new">
                <FilePlus2 /> {t("action.new")}
              </Link>
            </Button>
          )
        }
      />
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          aria-label="Search quotes"
          placeholder="Search by number or customer"
          className="pl-9"
          value={search}
          onChange={(e) => set("search", e.target.value)}
        />
      </div>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            role="tab"
            aria-selected={status === f.value}
            onClick={() => set("status", f.value)}
            className={cn(
              "h-9 shrink-0 rounded-full border px-4 text-sm font-medium",
              status === f.value
                ? "border-primary bg-primary text-primary-foreground"
                : "bg-background hover:bg-muted",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {!isLoading && !data?.results.length ? (
        <EmptyState icon={<FileSignature />} title="No quotes here">
          {canWrite && !status && !search && (
            <Button asChild>
              <Link to="/quotes/new">Create a quote</Link>
            </Button>
          )}
        </EmptyState>
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-y">
            {data?.results.map((q) => (
              <li key={q.id}>
                <Link
                  to={`/quotes/${q.id}`}
                  className="hover:bg-muted/50 flex items-center justify-between gap-3 px-4 py-3"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{q.customer.name}</span>
                    <span className="text-muted-foreground block text-xs">
                      {q.number} · valid until {formatDate(q.valid_until)}
                    </span>
                  </span>
                  <span className="flex flex-col items-end gap-1">
                    <span className="font-semibold whitespace-nowrap tabular-nums">
                      {formatMoney(q.total, q.currency)}
                    </span>
                    <StatusBadge status={q.display_status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {data && data.count > data.results.length && (
        <p className="text-muted-foreground text-center text-xs">
          Showing {data.results.length} of {data.count}. Use search to narrow it down.
        </p>
      )}
    </div>
  );
}
