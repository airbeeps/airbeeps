/**
 * Authentication helpers for E2E tests.
 */

import { Page, expect } from "@playwright/test";

/**
 * Register a new user via the UI.
 */
export async function registerUser(
  page: Page,
  email: string,
  password: string,
  options?: { name?: string }
) {
  await page.goto("/sign-up");

  // Fill in the registration form
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);

  if (options?.name) {
    const nameInput = page.getByLabel("Name");
    if (await nameInput.isVisible()) {
      await nameInput.fill(options.name);
    }
  }

  // Submit the form
  await page.getByRole("button", { name: /sign up|register/i }).click();

  // Wait for navigation or success
  await expect(page).toHaveURL(/\/(chat|admin|$)/, { timeout: 10000 });
}

/**
 * Login via the UI.
 */
export async function loginUser(page: Page, email: string, password: string) {
  await page.goto("/sign-in");

  // Fill in the login form
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);

  // Submit the form
  await page.getByRole("button", { name: /sign in|login/i }).click();

  // Wait for navigation
  await expect(page).toHaveURL(/\/(chat|admin|$)/, { timeout: 10000 });
}

/**
 * Logout via the UI.
 */
export async function logoutUser(page: Page) {
  // Click user menu and logout
  // This may vary based on your UI implementation
  const userMenu = page.locator('[data-testid="user-menu"]');
  if (await userMenu.isVisible()) {
    await userMenu.click();
    await page.getByRole("menuitem", { name: /logout|sign out/i }).click();
    await expect(page).toHaveURL(/sign-in/);
  }
}
