import { AlertTriangle, CircleDollarSign, FilePlus2, FileText, Wallet } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { useAccess, useMe } from "@/api/auth";
import { useDashboard, type Dashboard } from "@/api/resources";
import { EmptyState, PageHeader } from "@/components/page";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";

function amounts(rows: Dashboard["owed"]): string {
  if (!rows.length) return formatMoney(0);
  return rows.map((r) => formatMoney(r.amount, r.currency)).join(" · ");
}

function Stat({
  label,
  value,
  hint,
  icon,
  tone,
  to,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: ReactNode;
  tone?: "danger";
  to: string;
}) {
  return (
    <Link to={to} className="focus-visible:ring-ring/50 block rounded-xl focus-visible:ring-[3px]">
      <Card className="hover:bg-muted/50 gap-2 py-4 transition-colors">
        <CardContent className="flex items-start justify-between gap-2 px-4">
          <div className="min-w-0">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              {label}
            </p>
            <p
              className={cn(
                "mt-1 truncate text-xl font-semibold",
                tone === "danger" && "text-destructive",
              )}
            >
              {value}
            </p>
            {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
          </div>
          <span className="text-muted-foreground [&_svg]:size-5">{icon}</span>
        </CardContent>
      </Card>
    </Link>
  );
}

export function DashboardPage() {
  const { data: me } = useMe();
  const { canWrite } = useAccess();
  const t = useT();
  const { data, isLoading } = useDashboard();
  const overdueCount = data?.overdue.reduce((n, r) => n + r.count, 0) ?? 0;

  return (
    <div className="grid gap-6">
      <PageHeader
        title={`${t("dash.hello")}${me?.user.full_name ? `, ${me.user.full_name.split(" ")[0]}` : ""}`}
        description={t("dash.subtitle")}
        actions={
          canWrite && (
            <Button asChild>
              <Link to="/invoices/new">
                <FilePlus2 /> {t("action.newInvoice")}
              </Link>
            </Button>
          )
        }
      />

      {me?.current_business?.compliance_notice && (
        <div className="border-warning/60 bg-warning/10 flex gap-2 rounded-lg border p-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          {me.current_business.compliance_notice}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat
          label="Owed to you"
          value={isLoading ? "…" : amounts(data?.owed ?? [])}
          icon={<Wallet />}
          to="/invoices?status=unpaid"
        />
        <Stat
          label="Overdue"
          value={isLoading ? "…" : amounts(data?.overdue ?? [])}
          hint={overdueCount ? `${overdueCount} invoice${overdueCount > 1 ? "s" : ""}` : undefined}
          tone={overdueCount ? "danger" : undefined}
          icon={<AlertTriangle />}
          to="/invoices?status=overdue"
        />
        <Stat
          label="Paid this month"
          value={isLoading ? "…" : amounts(data?.paid_this_month ?? [])}
          icon={<CircleDollarSign />}
          to="/invoices?status=paid"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top debtors</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.top_debtors.length ? (
              <ul className="divide-y">
                {data.top_debtors.map((d) => (
                  <li key={`${d.customer_id}-${d.currency}`}>
                    <Link
                      to={`/invoices?customer=${d.customer_id}`}
                      className="hover:text-primary flex items-center justify-between gap-3 py-3"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{d.name}</span>
                        <span className="text-muted-foreground text-xs">
                          {d.invoices} unpaid invoice{d.invoices > 1 ? "s" : ""}
                        </span>
                      </span>
                      <span className="font-semibold whitespace-nowrap">
                        {formatMoney(d.balance, d.currency)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">Nobody owes you anything. 🎉</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent invoices</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.recent.length ? (
              <ul className="divide-y">
                {data.recent.map((inv) => (
                  <li key={inv.id}>
                    <Link
                      to={`/invoices/${inv.id}`}
                      className="hover:text-primary flex items-center justify-between gap-3 py-3"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{inv.customer.name}</span>
                        <span className="text-muted-foreground text-xs">
                          {inv.number} · {formatDate(inv.issue_date)}
                        </span>
                      </span>
                      <span className="flex flex-col items-end gap-1">
                        <span className="font-semibold whitespace-nowrap">
                          {formatMoney(inv.total, inv.currency)}
                        </span>
                        <StatusBadge status={inv.display_status} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              !isLoading && (
                <EmptyState icon={<FileText />} title="No invoices yet">
                  {canWrite && (
                    <Button asChild size="sm">
                      <Link to="/invoices/new">Create your first invoice</Link>
                    </Button>
                  )}
                </EmptyState>
              )
            )}
          </CardContent>
        </Card>
      </div>
      {!!data?.drafts && (
        <p className="text-muted-foreground text-sm">
          You have{" "}
          <Link className="text-primary underline" to="/invoices?status=draft">
            {data.drafts} draft{data.drafts > 1 ? "s" : ""}
          </Link>{" "}
          not sent yet.
        </p>
      )}
    </div>
  );
}
