/**
 * Money is integer minor units (ngwee) everywhere. Never use floats for amounts:
 * parse strings digit by digit and do totals with integer / BigInt maths.
 */

const SYMBOLS: Record<string, string> = { ZMW: "K", USD: "$" };

export function currencyPrefix(currency: string | undefined): string {
  return SYMBOLS[currency ?? "ZMW"] ?? "K";
}

export function formatMoney(amount: number, currency = "ZMW"): string {
  const symbol = SYMBOLS[currency] ?? `${currency} `;
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(Math.trunc(amount));
  const major = Math.floor(abs / 100).toLocaleString("en-US");
  const minor = String(abs % 100).padStart(2, "0");
  return `${sign}${symbol}${major}.${minor}`;
}

/** "1,234.5" → 123450. Returns null for anything that isn't a plain non-negative amount. */
export function parseMoney(input: string): number | null {
  const cleaned = input.replace(/[\s,]/g, "").replace(/^[Kk$]/, "");
  const match = /^(\d{1,10})(?:\.(\d{0,2}))?$/.exec(cleaned);
  if (!match) return null;
  const [, major, minor = ""] = match;
  return Number(major) * 100 + Number(minor.padEnd(2, "0"));
}

/** 123450 → "1234.50" for an input field. */
export function toMoneyInput(amount: number | undefined | null): string {
  if (amount == null) return "";
  return `${Math.floor(amount / 100)}.${String(amount % 100).padStart(2, "0")}`;
}

/** "1.5" → 1500n thousandths, null if invalid or more than 3 decimals. */
export function parseQuantity(input: string): bigint | null {
  const match = /^(\d{1,9})(?:\.(\d{0,3}))?$/.exec(input.trim());
  if (!match) return null;
  const [, whole = "0", frac = ""] = match;
  return BigInt(whole) * 1000n + BigInt(frac.padEnd(3, "0") || "0");
}

function roundHalfUpDiv(numerator: bigint, denominator: bigint): bigint {
  const q = numerator / denominator;
  const r = numerator % denominator;
  return r * 2n >= denominator ? q + 1n : q;
}

export interface PreviewLine {
  quantity: string;
  unit_price: number;
  discount: number;
}

/** Same maths as the server (sum exactly, round half-up once). Preview only: the server decides. */
export function previewTotals(lines: PreviewLine[]) {
  let grossThousandths = 0n;
  let discount = 0n;
  for (const line of lines) {
    const q = parseQuantity(line.quantity);
    if (q == null || !Number.isFinite(line.unit_price)) continue;
    grossThousandths += q * BigInt(Math.trunc(line.unit_price));
    discount += BigInt(Math.trunc(line.discount || 0));
  }
  const subtotal = Number(roundHalfUpDiv(grossThousandths, 1000n));
  const discountTotal = Number(discount);
  return { subtotal, discount_total: discountTotal, total: subtotal - discountTotal };
}

export function lineAmount(line: PreviewLine): number {
  return previewTotals([line]).total;
}
