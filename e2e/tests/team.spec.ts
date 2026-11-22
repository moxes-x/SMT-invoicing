import { expect, test } from "@playwright/test";

test("owner invites an accountant, who joins from the link and can only look", async ({
  page,
  browser,
  baseURL,
}) => {
  const stamp = Date.now();
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Natasha Phiri");
  await page.getByLabel("Email").fill(`natasha+${stamp}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Phiri Builders");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  // Invite from More → Team
  await page.goto("/more");
  await page.getByRole("link", { name: "Team" }).click();
  await expect(page.getByText("Natasha Phiri (you)")).toBeVisible();
  const email = `mulenga+${stamp}@example.com`;
  await page.getByLabel("Their email").fill(email);
  await page.getByLabel("Role").selectOption("accountant");
  await page.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText(`Invite emailed to ${email}`)).toBeVisible();

  const share = await page
    .getByRole("link", { name: "Share invite on WhatsApp" })
    .getAttribute("href");
  const text = decodeURIComponent(new URL(share!).searchParams.get("text") ?? "");
  const link = text.match(/https?:\/\/\S+\/join\/[0-9a-f-]+/)![0];

  // The accountant opens the link logged out, signs up and comes back to join
  const ctx = await browser.newContext();
  const acc = await ctx.newPage();
  await acc.goto(new URL(new URL(link).pathname, baseURL).toString());
  await expect(acc.getByText("Join Phiri Builders")).toBeVisible();
  await acc.getByRole("link", { name: "Create an account" }).click();
  await expect(acc.getByLabel("Email")).toHaveValue(email);
  await acc.getByLabel("Your name").fill("Mulenga Banda");
  await acc.getByLabel("Password").fill("correct-horse-battery");
  await acc.getByRole("button", { name: "Create account" }).click();
  await acc.getByRole("button", { name: "Join Phiri Builders" }).click();
  await expect(acc.getByRole("heading", { name: /Hello, Mulenga/ })).toBeVisible();

  // Read-only: no way to create things
  await expect(acc.getByRole("link", { name: "New invoice" })).toHaveCount(0);
  await acc.goto("/customers");
  await expect(acc.getByRole("heading", { name: "Customers" })).toBeVisible();
  await expect(acc.getByRole("button", { name: "Add", exact: true })).toHaveCount(0);
  await acc.goto("/team");
  await expect(acc.getByText("Mulenga Banda (you)")).toBeVisible();
  await expect(acc.getByLabel("Their email")).toHaveCount(0);
  await ctx.close();

  // The owner sees them on the team and can change their role
  await page.reload();
  await expect(page.getByText("Invited")).toHaveCount(0);
  await page.getByLabel("Role for Mulenga Banda").selectOption("staff");
  await expect(page.getByLabel("Role for Mulenga Banda")).toHaveValue("staff");
});
