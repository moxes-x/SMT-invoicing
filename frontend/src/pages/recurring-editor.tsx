import { useNavigate, useParams, useSearchParams } from "react-router";

import { useMe } from "@/api/auth";
import { useAppConfig, useRecurring, useSaveRecurring } from "@/api/resources";
import { DocumentEditor, EditorLoading } from "@/components/document-editor";
import { emptyValues, linesToValues, toLineRequests } from "@/lib/document-form";

export function RecurringEditorPage() {
  const { id } = useParams();
  const scheduleId = id ? Number(id) : undefined;
  const { data: schedule, isLoading } = useRecurring(scheduleId);
  const { data: me } = useMe();
  const { data: config } = useAppConfig();
  const [params] = useSearchParams();
  const save = useSaveRecurring();
  const navigate = useNavigate();

  if (scheduleId && isLoading) return <EditorLoading />;

  const base = emptyValues(
    params.get("customer") ?? "",
    me?.current_business?.default_currency ?? "ZMW",
    "recurring",
  );
  const initial = schedule
    ? {
        ...base,
        customer_id: String(schedule.customer.id),
        currency: schedule.currency === "USD" ? ("USD" as const) : ("ZMW" as const),
        notes: schedule.notes ?? "",
        lines: linesToValues(schedule.lines),
        frequency: schedule.frequency,
        interval: String(schedule.interval ?? 1),
        start_date: schedule.start_date < base.start_date ? base.start_date : schedule.start_date,
        end_date: schedule.end_date ?? "",
        days_until_due: String(schedule.days_until_due ?? 14),
        send_mode: schedule.send_mode ?? "draft",
      }
    : base;

  return (
    <DocumentEditor
      mode="recurring"
      title={schedule ? "Edit repeating invoice" : "New repeating invoice"}
      description="We create the invoice for you on each date, at 6 AM Lusaka time."
      initial={initial}
      cancelTo="/recurring"
      submitLabel="Save schedule"
      whatsappApi={!!config?.whatsapp_api}
      onSave={async (v) => {
        const body = {
          customer_id: Number(v.customer_id),
          currency: v.currency,
          notes: v.notes,
          lines: toLineRequests(v.lines),
          frequency: v.frequency,
          interval: Number(v.interval),
          end_date: v.end_date || null,
          days_until_due: Number(v.days_until_due),
          send_mode: v.send_mode,
          // Only send start_date when it changes: moving it restarts the schedule.
          ...(!schedule || v.start_date !== initial.start_date ? { start_date: v.start_date } : {}),
        };
        await save.mutateAsync({ id: schedule?.id, ...body });
        navigate("/recurring");
      }}
    />
  );
}
