import { expect, test } from "@playwright/test";

test("app in Bemba; a Nyanja customer gets their invoice in Nyanja", async ({
  page,
  browser,
  baseURL,
}) => {
  await page
    .context()
    .route("https://wa.me/**", (route) =>
      route.fulfill({ contentType: "text/html", body: "<p>WhatsApp</p>" }),
    );
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Natasha Phiri");
  await page.getByLabel("Email").fill(`natasha+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Phiri Builders");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  // The app in Bemba
  await page.goto("/more");
  await page.getByRole("button", { name: "Icibemba" }).click();
  await expect(page.getByRole("heading", { name: "Fimbi" })).toBeVisible();
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "Abashita" })).toBeVisible();
  await nav.getByRole("link", { name: "Ku ng'anda" }).click();
  await expect(page.getByRole("heading", { name: /Mwapoleni, Natasha/ })).toBeVisible();

  // A customer who reads Nyanja
  await nav.getByRole("link", { name: "Abashita" }).click();
  await page.getByRole("button", { name: "Lundapo", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Tiyamike Banda");
  await page.getByLabel("WhatsApp number").fill("0966 555 222");
  await page.getByLabel(/Ululimi/).selectOption("ny");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("+260966555222")).toBeVisible();

  await page.goto("/invoices/new");
  await page.getByLabel("Customer", { exact: true }).selectOption({ label: "Tiyamike Banda" });
  await page.getByLabel("Description").fill("Kumanga khoma");
  await page.getByLabel("Unit price").fill("500");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Tacilatumwa", { exact: true })).toBeVisible(); // draft, in Bemba

  const [popup] = await Promise.all([
    page.waitForEvent("popup"),
    page.getByRole("button", { name: "Send on WhatsApp" }).click(),
  ]);
  await expect.poll(() => popup.url()).toContain("260966555222");
  const text = decodeURIComponent(new URL(popup.url()).searchParams.get("text") ?? "");
  await popup.close();
  expect(text).toMatch(/^Muli bwanji Tiyamike, iyi ndi invoice/);

  const link = text.match(/https?:\/\/\S+\/i\/[0-9a-f-]+\//)![0];
  const customer = await browser.newContext();
  const cpage = await customer.newPage();
  await cpage.goto(new URL(new URL(link).pathname, baseURL).toString());
  await expect(cpage.getByRole("heading", { name: "Invoice", exact: true })).toBeVisible();
  await expect(cpage.getByText("Zotsala kulipira")).toBeVisible();
  await expect(cpage.getByRole("link", { name: "Tsitsani PDF" })).toBeVisible();
  await customer.close();
});
