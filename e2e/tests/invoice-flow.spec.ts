import { expect, test } from "@playwright/test";

test("sign up → customer → invoice → WhatsApp → customer opens link → payment → dashboard", async ({
  page,
  browser,
  baseURL,
}) => {
  // wa.me isn't reachable from CI; we only care about the URL the app opens.
  await page.context().route("https://wa.me/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<p>WhatsApp</p>" }),
  );

  // Sign up and onboard
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Mwila Banda");
  await page.getByLabel("Email").fill(`mwila+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Mwila Hair Studio");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Mwila/ })).toBeVisible();

  // Payment details shown on invoices
  await page.goto("/settings");
  await page.getByLabel("How customers pay you").fill("MTN MoMo 096 123 4567 (Mwila Banda)");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  // Customer
  await page.goto("/customers");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Chileshe Mulenga");
  await page.getByLabel("WhatsApp number").fill("0977 123 456");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("+260977123456")).toBeVisible();

  // Invoice: K450 x1 with K50 discount + 2 x K150 = K700
  await page.goto("/invoices/new");
  await page.getByLabel("Customer", { exact: true }).selectOption({ label: "Chileshe Mulenga" });
  await page.getByLabel("Description").fill("Box braids");
  await page.getByLabel("Unit price").fill("450");
  await page.getByRole("button", { name: "Add discount" }).click();
  await page.getByLabel("Discount on this line").fill("50");
  await page.getByRole("button", { name: "Add line" }).click();
  await page.getByLabel("Description").nth(1).fill("Hair treatment");
  await page.getByLabel("Qty").nth(1).fill("2");
  await page.getByLabel("Unit price").nth(1).fill("150");
  await expect(page.getByTestId("preview-total")).toHaveText("K700.00");
  await page.getByRole("button", { name: "Save draft" }).click();

  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  const number = (await page.locator("p", { hasText: /^INV-\d{4}-\d{4}$/ }).textContent())!;

  // Send via WhatsApp click-to-chat (opens a new tab to wa.me)
  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", { name: "Send on WhatsApp" }).click(),
  ]);
  await expect.poll(() => popup.url()).toContain("260977123456");
  const waText = decodeURIComponent(new URL(popup.url()).searchParams.get("text") ?? "");
  await popup.close();
  expect(waText).toContain(number);
  expect(waText).toContain("K700.00");
  const publicUrl = waText.match(/https?:\/\/\S+\/i\/[0-9a-f-]+\//)![0];
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();

  // Customer opens the link in their own (logged-out) browser
  const customer = await browser.newContext();
  const cpage = await customer.newPage();
  await cpage.goto(new URL(new URL(publicUrl).pathname, baseURL).toString());
  await expect(cpage.getByRole("heading", { name: "Invoice", exact: true })).toBeVisible();
  await expect(cpage.getByText("MTN MoMo 096 123 4567")).toBeVisible();
  await expect(cpage.getByText("Tax Invoice", { exact: true })).toHaveCount(0);
  await customer.close();

  await page.reload();
  await expect(page.getByText("Viewed", { exact: true })).toBeVisible();
  await expect(page.getByText("Viewed by customer")).toBeVisible();

  // Part payment, then the rest
  await page.getByRole("button", { name: "Record payment" }).click();
  await page.getByLabel("Amount", { exact: true }).fill("200");
  await page.getByLabel("Reference (optional)").fill("MP241122.1234");
  await page.getByRole("button", { name: "Save payment" }).click();
  await expect(page.getByText("Partly paid", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Record payment" }).click();
  await page.getByRole("button", { name: "Save payment" }).click(); // defaults to the balance
  await expect(page.getByText("Paid", { exact: true })).toBeVisible();

  // Dashboard
  await page.getByRole("link", { name: "Home" }).click();
  await expect(page.getByText("Paid this month")).toBeVisible();
  await expect(page.locator("a", { hasText: "Paid this month" })).toContainText("K700.00");
  await expect(page.locator("a", { hasText: "Owed to you" })).toContainText("K0.00");
});
