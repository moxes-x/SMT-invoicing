import { expect, test } from "@playwright/test";

test("sign up, create a business, see the dashboard, log out", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole("link", { name: "Create an account" }).click();

  await page.getByLabel("Your name").fill("Mwila Banda");
  await page.getByLabel("Email").fill(`mwila+${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByLabel("Business name").fill("Mwila Hair Studio");
  await page.getByLabel("Phone (optional)").fill("0971234567");
  await page.getByText("No", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("banner")).toContainText("Mwila Hair Studio");
  await expect(page.getByRole("heading", { name: "Hello, Mwila" })).toBeVisible();

  await page.getByRole("link", { name: "More" }).click();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
