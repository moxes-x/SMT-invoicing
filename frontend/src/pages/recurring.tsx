import { Pause, Pencil, Play, Plus, Repeat, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAccess } from "@/api/auth";
import {
  useDeleteRecurring,
  useRecurringList,
  useSaveRecurring,
  type Recurring,
} from "@/api/resources";
import { EmptyState, ErrorNote, PageHeader } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDate } from "@/lib/dates";
import { formatMoney } from "@/lib/money";
import { errorText } from "@/lib/send";

const SEND_MODE: Record<NonNullable<Recurring["send_mode"]>, string> = {
  draft: "kept as a draft for you to send",
  email: "emailed automatically",
  whatsapp: "sent on WhatsApp automatically",
};

function describeSchedule(r: Pick<Recurring, "frequency" | "interval">): string {
  const n = r.interval ?? 1;
  const unit = r.frequency === "weekly" ? "week" : "month";
  return n === 1 ? `Every ${unit}` : `Every ${n} ${unit}s`;
}

export function RecurringPage() {
  const { canWrite } = useAccess();
  const { data, isLoading } = useRecurringList();

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Repeating invoices"
        description="For rent, school fees, subscriptions: we create the invoice on each date."
        actions={
          canWrite && (
            <Button asChild>
              <Link to="/recurring/new">
                <Plus /> New
              </Link>
            </Button>
          )
        }
      />
      {!isLoading && !data?.results.length ? (
        <EmptyState icon={<Repeat />} title="No repeating invoices yet">
          {canWrite && (
            <Button asChild>
              <Link to="/recurring/new">Set one up</Link>
            </Button>
          )}
        </EmptyState>
      ) : (
        data?.results.map((r) => <ScheduleCard key={r.id} schedule={r} />)
      )}
    </div>
  );
}

function ScheduleCard({ schedule: r }: { schedule: Recurring }) {
  const save = useSaveRecurring();
  const remove = useDeleteRecurring();
  const { canWrite, canManage } = useAccess();
  const [error, setError] = useState<string | null>(null);
  const finished = !!r.end_date && r.next_run_date > r.end_date;
  const active = (r.is_active ?? true) && !finished;

  const toggle = async () => {
    setError(null);
    try {
      await save.mutateAsync({ id: r.id, is_active: !active });
    } catch (err) {
      setError(errorText(err, "Couldn't update the schedule."));
    }
  };

  return (
    <Card className="gap-3">
      <CardContent className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-semibold">{r.customer.name}</p>
            <p className="text-muted-foreground text-sm">
              {describeSchedule(r)} · {formatMoney(r.total, r.currency ?? "ZMW")}
            </p>
          </div>
          <Badge tone={finished ? "neutral" : active ? "success" : "warning"}>
            {finished ? "Finished" : active ? "Active" : "Paused"}
          </Badge>
        </div>
        <p className="text-sm">
          {active && r.upcoming.length > 0 ? (
            <>
              Next invoice <strong>{formatDate(r.upcoming[0])}</strong>
              {r.upcoming.length > 1 &&
                `, then ${r.upcoming.slice(1, 3).map(formatDate).join(", ")}`}
              . It will be {SEND_MODE[r.send_mode ?? "draft"]}.
            </>
          ) : (
            <span className="text-muted-foreground">
              {finished
                ? "This schedule has ended."
                : "Paused. Resume to carry on from the next date."}
            </span>
          )}
        </p>
        <p className="text-muted-foreground text-xs">
          {r.invoice_count} invoice{r.invoice_count === 1 ? "" : "s"} created so far
          {r.end_date && ` · ends ${formatDate(r.end_date)}`}
        </p>
        <div className="flex flex-wrap gap-2">
          {canWrite && (
            <Button asChild variant="outline" size="sm">
              <Link to={`/recurring/${r.id}/edit`}>
                <Pencil /> Edit
              </Link>
            </Button>
          )}
          {canWrite && !finished && (
            <Button variant="outline" size="sm" onClick={toggle} disabled={save.isPending}>
              {active ? <Pause /> : <Play />} {active ? "Pause" : "Resume"}
            </Button>
          )}
          {canManage && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm("Delete this schedule? Invoices already created stay.")) {
                  remove.mutate(r.id);
                }
              }}
            >
              <Trash2 /> Delete
            </Button>
          )}
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
      </CardContent>
    </Card>
  );
}
