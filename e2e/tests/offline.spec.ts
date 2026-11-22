import { expect, test } from "@playwright/test";

// The service worker (opening the app offline) only runs in the production build; see the
// README for checking it with `pnpm preview`. This covers saved data and the offline queue.
test("offline: saved data still shows, a new customer waits and is sent on reconnect", async ({
  page,
  context,
}) => {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Natasha Phiri");
  await page.getByLabel("Email").fill(`natasha+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Business name").fill("Phiri Builders");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  const nav = page.getByRole("navigation");
  await nav.getByRole("link", { name: "Customers" }).click();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Bwalya Tembo");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByText("Bwalya Tembo")).toBeVisible();
  await nav.getByRole("link", { name: "Home" }).click();
  await expect(page.getByRole("heading", { name: /Hello, Natasha/ })).toBeVisible();

  await context.setOffline(true);
  await expect(page.getByRole("status")).toContainText("You're offline");
  await nav.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByText("Bwalya Tembo")).toBeVisible();

  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Chanda Mwale");
  await page.getByRole("button", { name: "Add customer" }).click();
  await expect(page.getByRole("status")).toContainText("1 change will be sent");

  await context.setOffline(false);
  await expect(page.getByText("Chanda Mwale")).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
});
