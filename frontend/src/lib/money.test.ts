import { describe, expect, it } from "vitest";

import { formatMoney, parseMoney, parseQuantity, previewTotals, toMoneyInput } from "./money";

describe("money", () => {
  it("formats ngwee", () => {
    expect(formatMoney(123456)).toBe("K1,234.56");
    expect(formatMoney(5, "USD")).toBe("$0.05");
    expect(formatMoney(-150)).toBe("-K1.50");
  });

  it.each([
    ["1234.5", 123450],
    ["1,234.50", 123450],
    ["K 20", 2000],
    ["0.07", 7],
    ["12.", 1200],
  ])("parses %s", (input, expected) => {
    expect(parseMoney(input)).toBe(expected);
  });

  it.each(["", "abc", "-5", "1.234", "1e3"])("rejects %s", (input) => {
    expect(parseMoney(input)).toBeNull();
  });

  it("round-trips through input format", () => {
    expect(toMoneyInput(123405)).toBe("1234.05");
    expect(parseMoney(toMoneyInput(123405))).toBe(123405);
  });

  it("parses quantities to thousandths", () => {
    expect(parseQuantity("1.5")).toBe(1500n);
    expect(parseQuantity("0.333")).toBe(333n);
    expect(parseQuantity("1.2345")).toBeNull();
  });

  it("matches the server: sum exactly, round half-up once", () => {
    const line = { quantity: "0.333", unit_price: 5, discount: 0 };
    expect(previewTotals([line, line, line]).total).toBe(5);
    expect(
      previewTotals([
        { quantity: "2", unit_price: 12500, discount: 1000 },
        { quantity: "1.5", unit_price: 10000, discount: 0 },
      ]),
    ).toEqual({ subtotal: 40000, discount_total: 1000, total: 39000 });
  });
});
