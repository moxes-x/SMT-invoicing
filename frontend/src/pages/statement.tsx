import { ArrowLeft, Download } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useMe } from "@/api/auth";
import { statementQuery, useCustomer, useStatement, type StatementParams } from "@/api/resources";
import { FormField } from "@/components/form-field";
import { ErrorNote, PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { addDays, formatDate, todayISO } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

export function StatementPage() {
  const id = Number(useParams().id);
  const { data: customer } = useCustomer(id);
  const { data: me } = useMe();
  const today = todayISO();
  const [params, setParams] = useState<StatementParams>({
    start: addDays(today, -90),
    end: today,
    currency: me?.current_business?.default_currency === "USD" ? "USD" : "ZMW",
  });
  const { data: st, error, isLoading } = useStatement(id, params);
  const set = (patch: Partial<StatementParams>) => setParams((p) => ({ ...p, ...patch }));
  const c = params.currency;

  return (
    <div className="grid gap-4">
      <Button asChild variant="ghost" size="sm" className="justify-self-start">
        <Link to="/customers">
          <ArrowLeft /> Customers
        </Link>
      </Button>
      <PageHeader
        title="Statement"
        description={customer?.name}
        actions={
          <Button asChild>
            <a href={`/api/customers/${id}/statement/pdf/${statementQuery(params)}`}>
              <Download /> PDF
            </a>
          </Button>
        }
      />
      <Card>
        <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <FormField id="st-start" label="From">
            <Input
              id="st-start"
              type="date"
              value={params.start}
              max={params.end}
              onChange={(e) => e.target.value && set({ start: e.target.value })}
            />
          </FormField>
          <FormField id="st-end" label="To">
            <Input
              id="st-end"
              type="date"
              value={params.end}
              min={params.start}
              onChange={(e) => e.target.value && set({ end: e.target.value })}
            />
          </FormField>
          <FormField id="st-cur" label="Currency">
            <Select
              id="st-cur"
              value={params.currency}
              onChange={(e) => set({ currency: e.target.value as "ZMW" | "USD" })}
            >
              <option value="ZMW">ZMW</option>
              <option value="USD">USD</option>
            </Select>
          </FormField>
        </CardContent>
      </Card>
      {error && <ErrorNote>Couldn't load the statement. Check the dates.</ErrorNote>}
      {isLoading && <p className="text-muted-foreground text-sm">Loading…</p>}
      {st && (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            <Total label="Invoiced" value={formatMoney(st.invoiced, c)} />
            <Total label="Paid" value={formatMoney(st.paid, c)} />
            <Total label="Owed" value={formatMoney(st.closing, c)} strong />
          </div>
          <Card className="gap-0 py-0">
            <ul className="divide-y text-sm">
              <Row
                date={st.start}
                text="Opening balance"
                amount=""
                balance={formatMoney(st.opening, c)}
              />
              {st.rows.map((r, i) => (
                <Row
                  key={i}
                  date={r.date}
                  text={r.description}
                  sub={r.kind === "payment" ? r.reference : undefined}
                  to={r.invoice_id ? `/invoices/${r.invoice_id}` : undefined}
                  amount={r.debit ? formatMoney(r.debit, c) : `−${formatMoney(r.credit, c)}`}
                  credit={!!r.credit}
                  balance={formatMoney(r.balance, c)}
                />
              ))}
              <Row
                date={st.end}
                text="Closing balance"
                amount=""
                balance={formatMoney(st.closing, c)}
                bold
              />
            </ul>
          </Card>
          {st.rows.length === 0 && (
            <p className="text-muted-foreground text-center text-sm">
              Nothing invoiced or paid in these dates.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function Total({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="bg-card rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className={cn("font-semibold tabular-nums", strong && "text-primary")}>{value}</p>
    </div>
  );
}

function Row({
  date,
  text,
  sub,
  to,
  amount,
  credit,
  balance,
  bold,
}: {
  date: string;
  text: string;
  sub?: string;
  to?: string;
  amount: string;
  credit?: boolean;
  balance: string;
  bold?: boolean;
}) {
  return (
    <li className={cn("flex items-start justify-between gap-3 px-4 py-3", bold && "font-semibold")}>
      <span className="min-w-0">
        <span className="text-muted-foreground block text-xs">{formatDate(date)}</span>
        {to ? (
          <Link to={to} className="hover:underline">
            {text}
          </Link>
        ) : (
          <span>{text}</span>
        )}
        {sub && <span className="text-muted-foreground block text-xs">{sub}</span>}
      </span>
      <span className="shrink-0 text-right tabular-nums">
        {amount && (
          <span className={cn("block", credit && "text-emerald-700 dark:text-emerald-400")}>
            {amount}
          </span>
        )}
        <span className="text-muted-foreground block text-xs">Bal. {balance}</span>
      </span>
    </li>
  );
}
