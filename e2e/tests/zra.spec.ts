import { expect, test } from "@playwright/test";

// Needs the fake VSDC: node fake-vsdc.mjs (port 8091).
test("ZRA Smart Invoice: set up in Settings, send a tax invoice, void it with a credit note", async ({
  page,
}) => {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Natasha Phiri");
  await page.getByLabel("Email").fill(`natasha+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Phiri Hardware");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  // Business details: TPIN and VAT registration
  await page.goto("/settings");
  await page.getByLabel("TPIN (optional)").fill("1000000000");
  await page.getByLabel("We are VAT-registered").check();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("TPIN: 1000000000")).toBeVisible();

  // The ZRA device details, all entered in the app
  await page.getByLabel("VSDC address").fill("http://localhost:8091/zrasandboxvsdc");
  await page.getByLabel("Device serial").fill("20180520000000");
  await page.getByLabel("Item class code").fill("50102518");
  await page.getByLabel("Report my invoices to ZRA").check();
  await page.getByRole("button", { name: "Save ZRA settings" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await page.getByRole("button", { name: "Test ZRA connection" }).click();
  await expect(page.getByText("Connected to the ZRA VSDC. SDC ID SDC0010000553.")).toBeVisible();

  await page.goto("/customers");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Lusaka Lodge");
  await page.getByLabel("Customer TPIN (optional)").fill("2000000000");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("Lusaka Lodge")).toBeVisible();

  await page.goto("/invoices/new");
  await page.getByLabel("Customer", { exact: true }).selectOption({ label: "Lusaka Lodge" });
  await page.getByLabel("Description").fill("Cement, 10 bags");
  await page.getByLabel("Unit price").fill("1160");
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.getByRole("button", { name: "Mark as sent" }).click();
  const zra = page.getByRole("region", { name: "ZRA Smart Invoice" });
  await expect(zra.getByText("Tax invoice, signed by ZRA")).toBeVisible();
  await expect(zra.getByText("SDC0010000553")).toBeVisible();
  await expect(zra.getByText("K160.00")).toBeVisible(); // 1160 × 16/116

  // The customer's page is a Tax Invoice with ZRA's signature
  const link = await page.evaluate(async () => {
    const id = location.pathname.split("/").pop();
    const res = await fetch(`/api/invoices/${id}/`);
    return (await res.json()).public_url as string;
  });
  const customerPage = await page.context().newPage();
  await customerPage.goto(new URL(link).pathname);
  await expect(customerPage.getByRole("heading", { name: "Tax Invoice" })).toBeVisible();
  await expect(customerPage.getByText("VAT summary")).toBeVisible();
  await expect(customerPage.getByText(/FAKESIGN/)).toBeVisible();
  await customerPage.close();

  await page.getByRole("button", { name: "Void", exact: true }).click();
  await page.getByLabel("Reason (optional)").fill("Wrong customer");
  await page.getByRole("button", { name: "Void invoice" }).click();
  await expect(zra.getByText(/Credit note CN-/)).toBeVisible();
});
