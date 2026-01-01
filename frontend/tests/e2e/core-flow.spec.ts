/**
 * Core flow E2E smoke test.
 *
 * This test validates the complete user journey:
 * 1. Register a new user (becomes admin)
 * 2. Create a model provider
 * 3. Create a model
 * 4. Create an assistant
 * 5. Start a chat and receive a response
 *
 * Uses the backend in test mode, which returns deterministic fake LLM responses.
 */

import { test, expect } from "@playwright/test";

// Test user credentials
const TEST_EMAIL = "e2e-admin@test.com";
const TEST_PASSWORD = "SecureTestPassword123!";

test.describe("Core Flow", () => {
  test.beforeEach(async ({ page }) => {
    // Clear any existing auth state
    await page.context().clearCookies();
  });

  test("complete user journey from registration to chat", async ({ page }) => {
    // Step 1: Register a new user (first user becomes admin)
    await test.step("Register as admin", async () => {
      await page.goto("/sign-up");

      // Wait for registration form to be ready
      await expect(page.getByLabel("Email")).toBeVisible({ timeout: 10000 });

      // Fill registration form
      await page.getByLabel("Email").fill(TEST_EMAIL);
      await page.getByLabel("Password", { exact: true }).fill(TEST_PASSWORD);

      // Fill confirm password if present
      const confirmPassword = page.getByLabel(/confirm password/i);
      const confirmVisible = await confirmPassword.isVisible().catch(() => false);
      if (confirmVisible) {
        await confirmPassword.fill(TEST_PASSWORD);
      }

      // Submit and wait for navigation
      await page.getByRole("button", { name: /sign up|register|create account/i }).click();

      // Should redirect to main app or admin
      await expect(page).toHaveURL(/\/(chat|admin|assistants|$)/, { timeout: 15000 });
    });

    // Step 2: Navigate to admin and create provider
    await test.step("Create model provider", async () => {
      await page.goto("/admin/model-providers");

      // Wait for page content to load
      await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10000 });

      // Wait for and click the add button
      const addButton = page.getByRole("button", { name: /add|create|new/i }).first();
      await expect(addButton).toBeVisible({ timeout: 5000 });
      await addButton.click();

      // Wait for form to appear and fill it
      await expect(page.getByLabel(/^name/i).first()).toBeVisible({ timeout: 5000 });
      await page.getByLabel(/^name/i).first().fill("test-provider");
      await page.getByLabel(/display name/i).fill("Test Provider");
      await page.getByLabel(/api.*url/i).fill("https://api.test.com/v1");
      await page.getByLabel(/api.*key/i).fill("test-key");

      // Submit and wait for success
      const submitButton = page.getByRole("button", { name: /save|create|submit/i });
      await submitButton.click();

      // Wait for success indication (toast, redirect, or row appearing)
      await expect(
        page.getByText(/success|created|saved/i).or(page.getByText("test-provider"))
      ).toBeVisible({ timeout: 10000 });
    });

    // Step 3: Create a model
    await test.step("Create model", async () => {
      await page.goto("/admin/models");

      // Wait for page to load
      await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10000 });

      // Click add button
      const addButton = page.getByRole("button", { name: /add|create|new/i }).first();
      await expect(addButton).toBeVisible({ timeout: 5000 });
      await addButton.click();

      // Wait for form and fill it
      await expect(page.getByLabel(/^name/i).first()).toBeVisible({ timeout: 5000 });
      await page.getByLabel(/^name/i).first().fill("test-model");
      await page.getByLabel(/display name/i).fill("Test Model");

      // Select provider
      const providerSelect = page.getByLabel(/provider/i);
      const providerVisible = await providerSelect.isVisible().catch(() => false);
      if (providerVisible) {
        await providerSelect.click();
        await expect(page.getByRole("option").first()).toBeVisible({ timeout: 3000 });
        await page.getByRole("option").first().click();
      }

      // Submit and wait for success
      await page.getByRole("button", { name: /save|create|submit/i }).click();

      // Wait for model to be created
      await expect(
        page.getByText(/success|created|saved/i).or(page.getByText("test-model"))
      ).toBeVisible({ timeout: 10000 });
    });

    // Step 4: Create an assistant
    await test.step("Create assistant", async () => {
      await page.goto("/admin/assistants");

      // Wait for page to load
      await expect(page.locator("h1, h2").first()).toBeVisible({ timeout: 10000 });

      // Click add button
      const addButton = page.getByRole("button", { name: /add|create|new/i }).first();
      await expect(addButton).toBeVisible({ timeout: 5000 });
      await addButton.click();

      // Wait for form and fill it
      await expect(page.getByLabel(/^name/i).first()).toBeVisible({ timeout: 5000 });
      await page.getByLabel(/^name/i).first().fill("E2E Test Assistant");

      // Select model
      const modelSelect = page.getByLabel(/model/i);
      const modelVisible = await modelSelect.isVisible().catch(() => false);
      if (modelVisible) {
        await modelSelect.click();
        await expect(page.getByRole("option").first()).toBeVisible({ timeout: 3000 });
        await page.getByRole("option").first().click();
      }

      // Submit and wait for success
      await page.getByRole("button", { name: /save|create|submit/i }).click();

      // Wait for assistant to be created
      await expect(
        page.getByText(/success|created|saved/i).or(page.getByText("E2E Test Assistant"))
      ).toBeVisible({ timeout: 10000 });
    });

    // Step 5: Start a chat
    await test.step("Send chat message and receive response", async () => {
      await page.goto("/chat");

      // Wait for chat interface to load - look for input area
      const chatInput = page
        .locator('[data-testid="chat-input"]')
        .or(page.getByRole("textbox"))
        .or(page.locator("textarea"))
        .first();

      await expect(chatInput).toBeVisible({ timeout: 10000 });

      // Select assistant if selector exists
      const assistantSelect = page.locator('[data-testid="assistant-select"]');
      const assistantSelectVisible = await assistantSelect.isVisible().catch(() => false);
      if (assistantSelectVisible) {
        await assistantSelect.click();
        await expect(page.getByRole("option").first()).toBeVisible({ timeout: 3000 });
        await page.getByRole("option").first().click();
      }

      // Type and send message
      await chatInput.fill("Hello, this is an E2E test message!");

      // Try send button first, fallback to Enter
      const sendButton = page
        .locator('[data-testid="send-message-btn"]')
        .or(page.getByRole("button", { name: /send/i }));
      const sendVisible = await sendButton
        .first()
        .isVisible()
        .catch(() => false);

      if (sendVisible) {
        await sendButton.first().click();
      } else {
        await chatInput.press("Enter");
      }

      // Wait for the deterministic test mode response
      await expect(page.getByText("TEST_MODE_RESPONSE")).toBeVisible({ timeout: 30000 });
    });
  });

  test("second user registration is not admin", async ({ page }) => {
    // Register a second user
    await page.goto("/sign-up");

    // Wait for form
    await expect(page.getByLabel("Email")).toBeVisible({ timeout: 10000 });

    await page.getByLabel("Email").fill("second-user@test.com");
    await page.getByLabel("Password", { exact: true }).fill(TEST_PASSWORD);

    const confirmPassword = page.getByLabel(/confirm password/i);
    const confirmVisible = await confirmPassword.isVisible().catch(() => false);
    if (confirmVisible) {
      await confirmPassword.fill(TEST_PASSWORD);
    }

    await page.getByRole("button", { name: /sign up|register|create account/i }).click();

    // Should succeed and redirect
    await expect(page).toHaveURL(/\/(chat|assistants|$)/, { timeout: 15000 });

    // Try to access admin
    await page.goto("/admin");

    // Wait for page to settle, then check access
    await page.waitForLoadState("networkidle");

    // Should either be redirected away OR see forbidden message
    const currentUrl = page.url();
    const isOnAdminPage = currentUrl.includes("/admin");

    if (isOnAdminPage) {
      // If on admin page, should see forbidden/access denied
      const forbidden = page.getByText(/forbidden|access denied|not authorized|permission/i);
      await expect(forbidden).toBeVisible({ timeout: 5000 });
    }
    // If redirected away from admin, that's also a valid outcome for non-admin user
  });
});
