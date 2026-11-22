import { expect, test, type Page } from "@playwright/test";

async function signUpWithCustomer(page: Page) {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Natasha Phiri");
  await page.getByLabel("Email").fill(`natasha+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Phiri Builders");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  await page.goto("/customers");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Bwalya Tembo");
  await page.getByLabel("WhatsApp number").fill("0966 555 111");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("+260966555111")).toBeVisible();
}

async function openWhatsApp(page: Page, button: string): Promise<string> {
  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", { name: button, exact: true }).click(),
  ]);
  await expect.poll(() => popup.url()).toContain("260966555111");
  const text = decodeURIComponent(new URL(popup.url()).searchParams.get("text") ?? "");
  await popup.close();
  return text;
}

test("quote → customer accepts → invoice → send → reminder", async ({
  page,
  browser,
  baseURL,
}) => {
  await page
    .context()
    .route("https://wa.me/**", (route) =>
      route.fulfill({ contentType: "text/html", body: "<p>WhatsApp</p>" }),
    );
  await signUpWithCustomer(page);

  // Quote: 3 x K1,200 = K3,600
  await page.getByRole("link", { name: "Quotes" }).click();
  await page.getByRole("link", { name: "New" }).click();
  await page.getByLabel("Customer", { exact: true }).selectOption({ label: "Bwalya Tembo" });
  await page.getByLabel("Description").fill("Plastering per room");
  await page.getByLabel("Qty").fill("3");
  await page.getByLabel("Unit price").fill("1200");
  await expect(page.getByTestId("preview-total")).toHaveText("K3,600.00");
  await page.getByRole("button", { name: "Save quote" }).click();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();

  const waText = await openWhatsApp(page, "Send on WhatsApp");
  expect(waText).toContain("K3,600.00");
  const publicUrl = waText.match(/https?:\/\/\S+\/q\/[0-9a-f-]+\//)![0];
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();

  // Customer accepts from their own browser
  const customer = await browser.newContext();
  const cpage = await customer.newPage();
  await cpage.goto(new URL(new URL(publicUrl).pathname, baseURL).toString());
  await expect(cpage.getByRole("heading", { name: "Quote", exact: true })).toBeVisible();
  await cpage.getByRole("button", { name: "Accept quote" }).click();
  await expect(cpage.getByText(/Accepted\. Phiri Builders will be in touch/)).toBeVisible();
  await customer.close();

  await page.reload();
  await expect(page.getByText("Accepted", { exact: true })).toBeVisible();

  // Convert to a draft invoice with the same lines
  await page.getByRole("button", { name: "Make invoice" }).click();
  await page.getByRole("button", { name: "Create draft invoice" }).click();
  await expect(page).toHaveURL(/\/invoices\/\d+$/);
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  await expect(page.getByText("Plastering per room")).toBeVisible();
  await expect(page.getByRole("link", { name: /^QUO-\d{4}-\d{4}$/ })).toBeVisible();

  // Send it, then chase it with a reminder
  await openWhatsApp(page, "Send on WhatsApp");
  await expect(page.getByText("Sent", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Send reminder" }).click();
  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("dialog").getByRole("button", { name: "Send reminder" }).click(),
  ]);
  await expect.poll(() => popup.url()).toContain("260966555111");
  const reminder = decodeURIComponent(new URL(popup.url()).searchParams.get("text") ?? "");
  await popup.close();
  expect(reminder).toContain("reminder");
  expect(reminder).toContain("K3,600.00");
  await expect(page.getByText(/1 reminder sent so far/)).toBeVisible();
  await expect(page.getByText("Reminder by WhatsApp")).toBeVisible();
});
