import type { DisplayStatus } from "@/api/resources";
import { Badge } from "@/components/ui/badge";

const STATUS: Record<
  DisplayStatus,
  { label: string; tone: "neutral" | "info" | "success" | "warning" | "danger" | "brand" }
> = {
  draft: { label: "Draft", tone: "neutral" },
  sent: { label: "Sent", tone: "info" },
  viewed: { label: "Viewed", tone: "brand" },
  partial: { label: "Partly paid", tone: "warning" },
  paid: { label: "Paid", tone: "success" },
  overdue: { label: "Overdue", tone: "danger" },
  void: { label: "Void", tone: "neutral" },
};

export function StatusBadge({ status }: { status: DisplayStatus }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone} className={status === "void" ? "line-through" : undefined}>
      {s.label}
    </Badge>
  );
}
