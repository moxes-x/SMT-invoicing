import { Download, FilePlus2, FileText, Search, X } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { qs, useCustomer, useInvoices } from "@/api/resources";
import { EmptyState, PageHeader } from "@/components/page";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDate } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const FILTERS = [
  { value: "", label: "All" },
  { value: "unpaid", label: "Unpaid" },
  { value: "overdue", label: "Overdue" },
  { value: "partial", label: "Part-paid" },
  { value: "paid", label: "Paid" },
  { value: "draft", label: "Drafts" },
  { value: "void", label: "Void" },
];

export function InvoicesPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const search = params.get("search") ?? "";
  const customerId = Number(params.get("customer")) || undefined;
  const { data, isLoading } = useInvoices({ status, search, customer: customerId });
  const { data: customer } = useCustomer(customerId);

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Invoices"
        actions={
          <>
            <Button asChild variant="outline" size="icon" aria-label="Export these invoices (CSV)">
              <a href={`/api/invoices/export/${qs({ status, search, customer: customerId })}`}>
                <Download />
              </a>
            </Button>
            <Button asChild>
              <Link to={customerId ? `/invoices/new?customer=${customerId}` : "/invoices/new"}>
                <FilePlus2 /> New
              </Link>
            </Button>
          </>
        }
      />
      <div className="relative">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          aria-label="Search invoices"
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
      {customer && (
        <div className="flex items-center gap-2 text-sm">
          Showing invoices for <strong>{customer.name}</strong>
          <Button variant="ghost" size="sm" onClick={() => set("customer", "")}>
            <X /> Clear
          </Button>
        </div>
      )}

      {!isLoading && !data?.results.length ? (
        <EmptyState icon={<FileText />} title="No invoices here">
          {!status && !search && (
            <Button asChild>
              <Link to="/invoices/new">Create an invoice</Link>
            </Button>
          )}
        </EmptyState>
      ) : (
        <Card className="gap-0 py-0">
          <ul className="divide-y">
            {data?.results.map((inv) => (
              <li key={inv.id}>
                <Link
                  to={`/invoices/${inv.id}`}
                  className="hover:bg-muted/50 flex items-center justify-between gap-3 px-4 py-3"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{inv.customer.name}</span>
                    <span className="text-muted-foreground block text-xs">
                      {inv.number} · due {formatDate(inv.due_date)}
                    </span>
                  </span>
                  <span className="flex flex-col items-end gap-1">
                    <span className="font-semibold whitespace-nowrap tabular-nums">
                      {formatMoney(
                        inv.display_status === "partial" ? inv.balance : inv.total,
                        inv.currency,
                      )}
                    </span>
                    <StatusBadge status={inv.display_status} />
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
