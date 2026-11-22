import { expect, test, type Page } from "@playwright/test";

async function invoice(page: Page, currency: "ZMW" | "USD", price: string, rate?: string) {
  await page.goto("/invoices/new");
  await page.getByLabel("Customer", { exact: true }).selectOption({ label: "Lusaka Lodge" });
  await page.getByLabel("Currency").selectOption(currency);
  if (rate) await page.getByLabel(/Exchange rate/).fill(rate);
  await page.getByLabel("Description").fill("Catering");
  await page.getByLabel("Unit price").fill(price);
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.getByRole("button", { name: "Mark as sent" }).click();
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();
}

test("invoices in two currencies → per-currency report with a Kwacha total", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Natasha Phiri");
  await page.getByLabel("Email").fill(`natasha+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Phiri Catering");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  await page.goto("/customers");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Lusaka Lodge");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("Lusaka Lodge")).toBeVisible();

  await invoice(page, "ZMW", "1000");
  await invoice(page, "USD", "100", "25");
  await expect(page.getByText(/K2,500\.00 at K25 = \$1/)).toBeVisible();
  await invoice(page, "USD", "40");
  await expect(page.getByText(/No exchange rate yet/)).toBeVisible();

  await page.goto("/more");
  await page.getByRole("link", { name: "Reports" }).click();
  await expect(page.getByRole("region", { name: "Kwacha (ZMW)" })).toBeVisible();
  const usd = page.getByRole("region", { name: "US Dollars (USD)" });
  await expect(usd.getByText("$140.00").first()).toBeVisible();
  const all = page.getByRole("region", { name: "Everything in Kwacha" });
  await expect(all.getByText("K3,500.00").first()).toBeVisible();
  await expect(all.getByText(/1 invoice has no rate yet/)).toBeVisible();

  // Add the missing rate on the invoice and the report counts it
  await page.goto("/invoices");
  await page.getByText("$40.00").first().click();
  await page.getByRole("button", { name: "Add rate" }).click();
  await page.getByLabel("Kwacha per $1").fill("25");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(/K1,000\.00 at K25 = \$1/)).toBeVisible();
  await page.goto("/reports");
  await expect(
    page.getByRole("region", { name: "Everything in Kwacha" }).getByText("K4,500.00").first(),
  ).toBeVisible();
});
