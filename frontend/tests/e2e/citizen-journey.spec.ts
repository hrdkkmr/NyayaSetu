import { expect, test } from "@playwright/test";

// Synthetic test user, created fresh for each run. Never a real person.
const unique = () => `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;

test("landing page explains the product and its limits", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(/not a substitute for a lawyer/i)).toBeVisible();
  await page.getByRole("button", { name: "हिन्दी" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("कानूनी");
});

test("protected pages redirect to login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard/);
});

test("citizen registers, describes a consumer problem and gets one question at a time", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("E2E Citizen");
  await page.getByLabel("Email address").fill(unique());
  await page.getByLabel("Password").fill("e2e-password-2026");
  await page.getByRole("checkbox", { name: /privacy notice/i }).click();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/cases\/new/);

  await page.getByRole("button", { name: /Describe it in writing/i }).click();
  await page.getByLabel("What happened?").fill(
    "I bought a laptop from Amazon on 12 March 2026 for Rs. 54,999 but it was delivered damaged and the seller refuses to replace it",
  );
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/cases\/.+tab=conversation/);
  await expect(page.getByText(/Is all of that correct\?/)).toBeVisible();
  await page.getByRole("button", { name: /all correct/i }).click();
  await expect(page.getByText(/When did the problem happen/)).toBeVisible();

  await page.getByRole("tab", { name: "Facts" }).click();
  await expect(page.getByText("Confirmed by you").first()).toBeVisible();
  await page.getByRole("tab", { name: "Filing" }).click();
  await expect(page.getByText(/approve all documents/i)).toBeVisible();
});
