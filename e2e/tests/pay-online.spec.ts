import { expect, test } from "@playwright/test";

// Needs the fake Lenco server (e2e/fake-lenco.mjs) and Django started with
// LENCO_SANDBOX_API_URL=http://localhost:8090/access/v2 (CI does this).
test("connect Lenco → customer pays with MTN → receipt → paid → statement → CSV", async ({
  page,
  browser,
  baseURL,
}) => {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Mutale Zulu");
  await page.getByLabel("Email").fill(`mutale+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Zulu Tailoring");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Mutale/ })).toBeVisible();

  // Connect Lenco (sandbox keys)
  await page.goto("/settings");
  await page.getByLabel("Show Pay now on my invoices").check();
  await page.getByLabel("Public key").fill("pub-sandbox-test");
  await page.getByLabel("Secret key").fill("sk-sandbox-test-1234");
  await page.getByRole("button", { name: "Save online payments" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Connected to Lenco.")).toBeVisible();

  // Customer whose number is Lenco's "successful" MTN sandbox number
  await page.goto("/customers");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Bupe Kunda");
  await page.getByLabel("WhatsApp number").fill("096 111 1111");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("+260961111111")).toBeVisible();

  await page.goto("/invoices/new");
  await page.getByLabel("Customer", { exact: true }).selectOption({ label: "Bupe Kunda" });
  await page.getByLabel("Description").fill("School uniform");
  await page.getByLabel("Unit price").fill("350");
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.getByRole("button", { name: "Mark as sent" }).click();
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();
  await expect(page.getByText(/can pay this online/)).toBeVisible();
  const publicPath = new URL(
    (await page.getByRole("link", { name: "Customer view" }).getAttribute("href"))!,
  ).pathname;

  // The customer pays from their own phone
  const customer = await browser.newContext();
  const cpage = await customer.newPage();
  await cpage.goto(new URL(publicPath, baseURL).toString());
  await expect(cpage.getByRole("heading", { name: "Pay K350.00 now" })).toBeVisible();
  await expect(cpage.getByLabel("Mobile money number")).toHaveValue("0961111111");
  await cpage.getByRole("button", { name: "Pay with mobile money" }).click();
  await expect(cpage.getByText("Check your phone.")).toBeVisible();
  // The page refreshes itself until Lenco confirms
  await expect(cpage.getByText("Payment received. Thank you!")).toBeVisible({ timeout: 15_000 });
  await cpage.getByRole("link", { name: "View your receipt" }).click();
  await expect(cpage.getByRole("heading", { name: "Receipt" })).toBeVisible();
  await expect(cpage.getByText(/RCT-\d{4}-0001/)).toBeVisible();
  await expect(cpage.getByText("MTN MoMo")).toBeVisible();
  await customer.close();

  // The owner sees it paid, online, with a receipt
  await page.reload();
  await expect(page.getByText("Paid", { exact: true })).toHaveCount(2); // badge + "Paid" figure
  await expect(page.getByText("Paid online", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open receipt" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete payment" })).toHaveCount(0);

  // Statement
  await page.goto("/customers");
  await page.getByRole("link", { name: "Statement for Bupe Kunda" }).click();
  await expect(page.getByText("Invoiced", { exact: true })).toBeVisible();
  await expect(page.getByText(/^Payment for INV-/)).toBeVisible();
  await expect(page.locator("div", { hasText: /^OwedK0\.00$/ })).toBeVisible();

  // CSV export
  const csv = await page.request.get("/api/payments/export/");
  expect(csv.headers()["content-type"]).toContain("text/csv");
  expect(await csv.text()).toContain(",Bupe Kunda,ZMW,350.00,MTN MoMo,Paid online,");
});
