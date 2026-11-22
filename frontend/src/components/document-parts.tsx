import type { ReactNode } from "react";

import type { Invoice } from "@/api/resources";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { cn } from "@/lib/utils";

type Currency = Invoice["currency"];
type Line = Invoice["lines"][number];
type Activity = Invoice["activity"][number];

export function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function Fact({
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
        className={cn(
          "font-semibold tabular-nums",
          strong && "text-primary",
          danger && "text-destructive",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div className={cn("flex justify-between", bold && "text-base font-semibold")}>
      <dt className={bold ? "" : "text-muted-foreground"}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

export function LinesCard({
  doc,
}: {
  doc: {
    currency?: Currency;
    lines: Line[];
    subtotal: number;
    discount_total: number;
    total: number;
    notes?: string;
  };
}) {
  const c = doc.currency ?? "ZMW";
  return (
    <Section title="Items">
      <ul className="divide-y">
        {doc.lines.map((l) => (
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
        {doc.discount_total > 0 && (
          <>
            <Row label="Subtotal" value={formatMoney(doc.subtotal, c)} />
            <Row label="Discount" value={`−${formatMoney(doc.discount_total, c)}`} />
          </>
        )}
        <Row label="Total" value={formatMoney(doc.total, c)} bold />
      </dl>
      {doc.notes && (
        <p className="text-muted-foreground mt-3 text-sm whitespace-pre-line">{doc.notes}</p>
      )}
    </Section>
  );
}

export function Timeline({ activity }: { activity: Activity[] }) {
  return (
    <Section title="Activity">
      <ol className="relative grid gap-4 border-l pl-5">
        {activity.map((a) => (
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
