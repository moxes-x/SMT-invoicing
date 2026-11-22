import type { DisplayStatus, QuoteDisplayStatus } from "@/api/resources";
import { Badge } from "@/components/ui/badge";
import { useT } from "@/i18n";

type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "brand";

const STATUS: Record<DisplayStatus | QuoteDisplayStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "neutral" },
  sent: { label: "Sent", tone: "info" },
  viewed: { label: "Viewed", tone: "brand" },
  partial: { label: "Partly paid", tone: "warning" },
  paid: { label: "Paid", tone: "success" },
  overdue: { label: "Overdue", tone: "danger" },
  void: { label: "Void", tone: "neutral" },
  accepted: { label: "Accepted", tone: "success" },
  declined: { label: "Declined", tone: "danger" },
  expired: { label: "Expired", tone: "warning" },
  converted: { label: "Invoiced", tone: "neutral" },
};

export function StatusBadge({ status }: { status: DisplayStatus | QuoteDisplayStatus }) {
  const s = STATUS[status];
  const t = useT();
  return (
    <Badge tone={s.tone} className={status === "void" ? "line-through" : undefined}>
      {t(`status.${status}`)}
    </Badge>
  );
}
