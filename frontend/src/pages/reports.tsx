import { Download } from "lucide-react";
import { useState } from "react";

import { qs, useReport, type CurrencyReport, type Report } from "@/api/resources";
import { Fact, Section } from "@/components/document-parts";
import { FormField } from "@/components/form-field";
import { PageHeader } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDate, todayISO } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

const CURRENCY_NAME: Record<string, string> = { ZMW: "Kwacha", USD: "US Dollars" };

type Range = { start: string; end: string };

const iso = (y: number, m: number, d: number) =>
  `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

/** Preset ranges, computed from today. Months are 0-based here, like Date. */
function presets(today: string): { key: string; label: string; range: Range }[] {
  const [y, m] = [Number(today.slice(0, 4)), Number(today.slice(5, 7)) - 1];
  const lastOfPrev = new Date(Date.UTC(y, m, 0));
  const q = Math.floor(m / 3) * 3;
  const year12 = new Date(Date.UTC(y, m - 11, 1));
  return [
    { key: "month", label: "This month", range: { start: iso(y, m, 1), end: today } },
    {
      key: "last",
      label: "Last month",
      range: {
        start: iso(lastOfPrev.getUTCFullYear(), lastOfPrev.getUTCMonth(), 1),
        end: lastOfPrev.toISOString().slice(0, 10),
      },
    },
    { key: "quarter", label: "This quarter", range: { start: iso(y, q, 1), end: today } },
    { key: "year", label: "This year", range: { start: iso(y, 0, 1), end: today } },
    {
      key: "12m",
      label: "Last 12 months",
      range: { start: iso(year12.getUTCFullYear(), year12.getUTCMonth(), 1), end: today },
    },
  ];
}

export function ReportsPage() {
  const today = todayISO();
  const options = presets(today);
  const [range, setRange] = useState<Range>(options[0]!.range);
  const { data, isLoading, isError } = useReport(range);
  const active = options.find(
    (o) => o.range.start === range.start && o.range.end === range.end,
  )?.key;

  return (
    <div className="grid grid-cols-1 gap-4">
      <PageHeader
        title="Reports"
        description="What you invoiced and collected, and who owes you. Each currency on its own."
        actions={
          <Button asChild variant="outline">
            <a href={`/api/reports/export/${qs(range)}`}>
              <Download /> CSV
            </a>
          </Button>
        }
      />

      <div className="grid gap-3">
        <div
          className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1"
          role="group"
          aria-label="Period"
        >
          {options.map((o) => (
            <Button
              key={o.key}
              size="sm"
              variant={active === o.key ? "default" : "outline"}
              aria-pressed={active === o.key}
              onClick={() => setRange(o.range)}
              className="shrink-0"
            >
              {o.label}
            </Button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <FormField id="r-start" label="From">
            <Input
              id="r-start"
              type="date"
              value={range.start}
              max={range.end}
              onChange={(e) => e.target.value && setRange({ ...range, start: e.target.value })}
            />
          </FormField>
          <FormField id="r-end" label="To">
            <Input
              id="r-end"
              type="date"
              value={range.end}
              min={range.start}
              onChange={(e) => e.target.value && setRange({ ...range, end: e.target.value })}
            />
          </FormField>
        </div>
      </div>

      {isError && (
        <p className="text-destructive text-sm">Couldn't load the report. Check the dates.</p>
      )}
      {isLoading || !data ? (
        !isError && <p className="text-muted-foreground text-sm">Loading…</p>
      ) : (
        <>
          {data.currencies.length > 1 && <KwachaCard data={data} />}
          {data.currencies.map((c) => (
            <CurrencySection key={c.currency} c={c} asOf={data.as_of} />
          ))}
        </>
      )}
    </div>
  );
}

function KwachaCard({ data }: { data: Report }) {
  const k = data.kwacha;
  return (
    <section aria-label="Everything in Kwacha">
      <Section title="Everything in Kwacha">
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Fact label="Invoiced" value={formatMoney(k.invoiced, "ZMW")} />
          <Fact label="Collected" value={formatMoney(k.collected, "ZMW")} strong />
          <Fact label="Owed now" value={formatMoney(k.outstanding, "ZMW")} />
          <Fact label="Overdue now" value={formatMoney(k.overdue, "ZMW")} danger={k.overdue > 0} />
        </div>
        <p className="text-muted-foreground mt-3 text-xs">
          Other currencies are converted at each invoice's own exchange rate.
          {k.missing_rates > 0 &&
            ` ${k.missing_rates} invoice${k.missing_rates === 1 ? " has" : "s have"} no rate yet and ${k.missing_rates === 1 ? "is" : "are"} left out. Add the rate on the invoice.`}
        </p>
      </Section>
    </section>
  );
}

function CurrencySection({ c, asOf }: { c: CurrencyReport; asOf: string }) {
  const cur = c.currency;
  const money = (n: number) => formatMoney(n, cur);
  const count = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return (
    <section aria-label={`${CURRENCY_NAME[cur] ?? cur} (${cur})`}>
      <Section title={`${CURRENCY_NAME[cur] ?? cur} (${cur})`}>
        <div className="grid gap-5">
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <Fact label="Invoiced" value={money(c.invoiced.amount)} />
              <p className="text-muted-foreground text-xs">{count(c.invoiced.count, "invoice")}</p>
            </div>
            <div>
              <Fact label="Collected" value={money(c.collected.amount)} strong />
              <p className="text-muted-foreground text-xs">{count(c.collected.count, "payment")}</p>
            </div>
            <div>
              <Fact label="Owed now" value={money(c.outstanding.amount)} />
              <p className="text-muted-foreground text-xs">
                {count(c.outstanding.count, "invoice")}
              </p>
            </div>
            <div>
              <Fact
                label="Overdue now"
                value={money(c.overdue.amount)}
                danger={c.overdue.amount > 0}
              />
              <p className="text-muted-foreground text-xs">{count(c.overdue.count, "invoice")}</p>
            </div>
          </div>

          {c.months.length > 1 && <MonthChart months={c.months} currency={cur} />}

          <div className="grid gap-5 sm:grid-cols-2">
            <BarList
              title="Collected by method"
              empty="No payments in this period."
              rows={c.by_method.map((m) => ({ key: m.method, label: m.name, amount: m.amount }))}
              money={money}
            />
            <BarList
              title={`Owed by age (as of ${formatDate(asOf)})`}
              empty="Nothing owed. Well done."
              rows={c.aging
                .filter((a) => a.amount > 0)
                .map((a) => ({ key: a.bucket, label: a.name, amount: a.amount }))}
              money={money}
            />
          </div>

          {c.top_customers.length > 0 && (
            <div>
              <h3 className="mb-2 text-sm font-medium">Top customers by invoiced</h3>
              <ol className="divide-y text-sm">
                {c.top_customers.map((t) => (
                  <li key={t.customer_id} className="flex justify-between gap-3 py-1.5">
                    <span className="min-w-0 truncate">{t.name}</span>
                    <span className="shrink-0 tabular-nums">{money(t.invoiced)}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </Section>
    </section>
  );
}

/** One-hue horizontal bars: a magnitude per row, labelled with its value. */
function BarList({
  title,
  empty,
  rows,
  money,
}: {
  title: string;
  empty: string;
  rows: { key: string; label: string; amount: number }[];
  money: (n: number) => string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.amount));
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-muted-foreground text-sm">{empty}</p>
      ) : (
        <ul className="grid gap-2 text-sm">
          {rows.map((r) => (
            <li key={r.key}>
              <div className="flex justify-between gap-3">
                <span className="min-w-0 truncate">{r.label}</span>
                <span className="shrink-0 tabular-nums">{money(r.amount)}</span>
              </div>
              <div className="bg-muted mt-1 h-1.5 rounded-full">
                <div
                  className="bg-series-invoiced h-full rounded-full"
                  style={{ width: `${Math.max(2, (r.amount / max) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthLabel = (key: string) => `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}`;

/** Invoiced vs collected per month: paired bars on one axis, with a hover/focus readout. */
function MonthChart({ months, currency }: { months: CurrencyReport["months"]; currency: string }) {
  const [active, setActive] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const max = Math.max(1, ...months.flatMap((m) => [m.invoiced, m.collected]));
  const shown = months[active ?? months.length - 1]!;
  const every = months.length > 12 ? 3 : months.length > 6 ? 2 : 1;
  const money = (n: number) => formatMoney(n, currency);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Month by month</h3>
        <div className="flex items-center gap-3 text-xs">
          <Legend color="bg-series-invoiced" label="Invoiced" />
          <Legend color="bg-series-collected" label="Collected" />
          <Button
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs"
            onClick={() => setTable(!table)}
          >
            {table ? "Chart" : "Table"}
          </Button>
        </div>
      </div>
      {table ? (
        <table className="w-full text-sm">
          <thead className="text-muted-foreground text-left text-xs">
            <tr>
              <th className="py-1 font-normal">Month</th>
              <th className="py-1 text-right font-normal">Invoiced</th>
              <th className="py-1 text-right font-normal">Collected</th>
            </tr>
          </thead>
          <tbody className="divide-y tabular-nums">
            {months.map((m) => (
              <tr key={m.month}>
                <td className="py-1">{monthLabel(m.month)}</td>
                <td className="py-1 text-right">{money(m.invoiced)}</td>
                <td className="py-1 text-right">{money(m.collected)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <p className="text-muted-foreground mb-2 text-xs tabular-nums" aria-live="polite">
            <span className="text-foreground font-medium">{monthLabel(shown.month)}</span>
            {" · "}Invoiced {money(shown.invoiced)} · Collected {money(shown.collected)}
          </p>
          <div className="flex h-36 items-end gap-1 border-b" onMouseLeave={() => setActive(null)}>
            {months.map((m, i) => (
              <button
                key={m.month}
                type="button"
                aria-label={`${monthLabel(m.month)}: invoiced ${money(m.invoiced)}, collected ${money(m.collected)}`}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onClick={() => setActive(i)}
                className={cn(
                  "flex h-full min-w-0 flex-1 items-end justify-center gap-[2px] rounded-sm outline-none focus-visible:ring-2",
                  active === i && "bg-muted",
                )}
              >
                <Bar value={m.invoiced} max={max} color="bg-series-invoiced" />
                <Bar value={m.collected} max={max} color="bg-series-collected" />
              </button>
            ))}
          </div>
          <div className="text-muted-foreground mt-1 flex gap-1 text-[10px]">
            {months.map((m, i) => (
              <span key={m.month} className="min-w-0 flex-1 truncate text-center">
                {i % every === 0 ? MONTHS[Number(m.month.slice(5, 7)) - 1] : ""}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <span
      className={cn("block w-full max-w-4 rounded-t-[4px]", color)}
      style={{ height: value > 0 ? `max(2px, ${(value / max) * 100}%)` : 0 }}
    />
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("size-2.5 rounded-sm", color)} />
      {label}
    </span>
  );
}
