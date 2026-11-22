/** Form values and conversions shared by the invoice, quote and recurring editors. */
import { z } from "zod";

import type { InvoiceLineRequest } from "@/api/resources";
import { addDays, todayISO } from "@/lib/dates";
import { parseMoney, parseQuantity, toMoneyInput } from "@/lib/money";

export type EditorMode = "invoice" | "quote" | "recurring";

const money = (msg: string) => z.string().refine((v) => parseMoney(v) !== null, msg);

const lineSchema = z
  .object({
    item: z.number().nullable(),
    description: z.string().trim().min(1, "Describe this line."),
    quantity: z
      .string()
      .refine((v) => (parseQuantity(v) ?? 0n) > 0n, "Quantity must be more than 0."),
    price: money("Enter a price like 150.00").refine(
      (v) => (parseMoney(v) ?? 0) > 0,
      "Price must be more than 0.",
    ),
    discount: z.string().refine((v) => v.trim() === "" || parseMoney(v) !== null, "Invalid amount"),
  })
  .refine(
    (l) => {
      const d = parseMoney(l.discount || "0") ?? 0;
      const p = parseMoney(l.price) ?? 0;
      const q = parseQuantity(l.quantity) ?? 0n;
      return BigInt(d) * 1000n <= q * BigInt(p);
    },
    { path: ["discount"], message: "Discount is more than the line value." },
  );

const baseSchema = z.object({
  customer_id: z.string().min(1, "Choose a customer."),
  currency: z.enum(["ZMW", "USD"]),
  notes: z.string(),
  lines: z.array(lineSchema).min(1, "Add at least one line."),
  // invoice / quote
  issue_date: z.string(),
  due_date: z.string(), // invoice: due date; quote: valid until
  // recurring
  frequency: z.enum(["weekly", "monthly"]),
  interval: z.string(),
  start_date: z.string(),
  end_date: z.string(),
  days_until_due: z.string(),
  send_mode: z.enum(["draft", "email", "whatsapp"]),
});

export type EditorValues = z.infer<typeof baseSchema>;
export type LineValues = EditorValues["lines"][number];

export function schemaFor(mode: EditorMode) {
  return baseSchema.superRefine((v, ctx) => {
    const need = (path: keyof EditorValues, ok: boolean, message: string) => {
      if (!ok) ctx.addIssue({ code: "custom", path: [path], message });
    };
    if (mode === "recurring") {
      need("start_date", !!v.start_date, "Pick a start date.");
      need("start_date", !v.start_date || v.start_date >= todayISO(), "Start today or later.");
      need("end_date", !v.end_date || v.end_date >= v.start_date, "End can't be before start.");
      need("interval", /^(?:[1-9]|1[0-2])$/.test(v.interval), "1 to 12.");
      need(
        "days_until_due",
        /^\d{1,3}$/.test(v.days_until_due) && Number(v.days_until_due) <= 120,
        "0 to 120 days.",
      );
    } else {
      need("issue_date", !!v.issue_date, "Pick a date.");
      need("due_date", !!v.due_date, "Pick a date.");
      need(
        "due_date",
        !v.due_date || !v.issue_date || v.due_date >= v.issue_date,
        mode === "quote"
          ? "Valid-until can't be before the date."
          : "Due date can't be before the issue date.",
      );
    }
  });
}

export const EMPTY_LINE: LineValues = {
  item: null,
  description: "",
  quantity: "1",
  price: "",
  discount: "",
};

export function emptyValues(
  customerId = "",
  currency = "ZMW",
  mode: EditorMode = "invoice",
): EditorValues {
  const today = todayISO();
  return {
    customer_id: customerId,
    currency: currency === "USD" ? "USD" : "ZMW",
    notes: "",
    lines: [EMPTY_LINE],
    issue_date: today,
    due_date: addDays(today, mode === "quote" ? 30 : 14),
    frequency: "monthly",
    interval: "1",
    start_date: today,
    end_date: "",
    days_until_due: "14",
    send_mode: "draft",
  };
}

export interface LineLike {
  item?: number | null;
  description: string;
  quantity: string;
  unit_price: number;
  discount?: number;
}

export function linesToValues(lines: LineLike[]): LineValues[] {
  return lines.map((l) => ({
    item: l.item ?? null,
    description: l.description,
    quantity: String(Number(l.quantity)),
    price: toMoneyInput(l.unit_price),
    discount: l.discount ? toMoneyInput(l.discount) : "",
  }));
}

export function toLineRequests(lines: LineValues[]): InvoiceLineRequest[] {
  return lines.map((l) => ({
    item: l.item,
    description: l.description.trim(),
    quantity: l.quantity.trim(),
    unit_price: parseMoney(l.price) ?? 0,
    discount: parseMoney(l.discount || "0") ?? 0,
  }));
}
