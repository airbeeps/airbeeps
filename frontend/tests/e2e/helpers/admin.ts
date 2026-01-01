/**
 * Admin helpers for E2E tests.
 */

import { Page, expect } from "@playwright/test";

/**
 * Navigate to admin section.
 */
export async function goToAdmin(page: Page) {
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin/);
}

/**
 * Create a model provider via admin UI.
 */
export async function createProvider(
  page: Page,
  options: {
    name: string;
    displayName: string;
    interfaceType?: string;
    apiBaseUrl: string;
    apiKey?: string;
  }
) {
  await page.goto("/admin/model-providers");

  // Click add provider button
  await page
    .getByRole("button", { name: /add|create|new/i })
    .first()
    .click();

  // Fill in the form
  await page.getByLabel(/name/i).first().fill(options.name);
  await page.getByLabel(/display name/i).fill(options.displayName);

  if (options.interfaceType) {
    const interfaceSelect = page.getByLabel(/interface type/i);
    if (await interfaceSelect.isVisible()) {
      await interfaceSelect.selectOption(options.interfaceType);
    }
  }

  await page.getByLabel(/api.*url/i).fill(options.apiBaseUrl);

  if (options.apiKey) {
    await page.getByLabel(/api.*key/i).fill(options.apiKey);
  }

  // Submit
  await page.getByRole("button", { name: /save|create|submit/i }).click();

  // Wait for success
  await expect(page.getByText(/success|created/i)).toBeVisible({ timeout: 5000 });
}

/**
 * Create a model via admin UI.
 */
export async function createModel(
  page: Page,
  options: {
    name: string;
    displayName: string;
    providerName: string;
  }
) {
  await page.goto("/admin/models");

  // Click add model button
  await page
    .getByRole("button", { name: /add|create|new/i })
    .first()
    .click();

  // Fill in the form
  await page.getByLabel(/^name/i).fill(options.name);
  await page.getByLabel(/display name/i).fill(options.displayName);

  // Select provider
  const providerSelect = page.getByLabel(/provider/i);
  if (await providerSelect.isVisible()) {
    await providerSelect.click();
    await page.getByRole("option", { name: options.providerName }).click();
  }

  // Submit
  await page.getByRole("button", { name: /save|create|submit/i }).click();

  // Wait for success
  await expect(page.getByText(/success|created/i)).toBeVisible({ timeout: 5000 });
}

/**
 * Create an assistant via admin UI.
 */
export async function createAssistant(
  page: Page,
  options: {
    name: string;
    modelName: string;
    systemPrompt?: string;
  }
) {
  await page.goto("/admin/assistants");

  // Click add assistant button
  await page
    .getByRole("button", { name: /add|create|new/i })
    .first()
    .click();

  // Fill in the form
  await page.getByLabel(/^name/i).fill(options.name);

  // Select model
  const modelSelect = page.getByLabel(/model/i);
  if (await modelSelect.isVisible()) {
    await modelSelect.click();
    await page.getByRole("option", { name: options.modelName }).click();
  }

  if (options.systemPrompt) {
    const promptInput = page.getByLabel(/system prompt/i);
    if (await promptInput.isVisible()) {
      await promptInput.fill(options.systemPrompt);
    }
  }

  // Submit
  await page.getByRole("button", { name: /save|create|submit/i }).click();

  // Wait for success
  await expect(page.getByText(/success|created/i)).toBeVisible({ timeout: 5000 });
}
