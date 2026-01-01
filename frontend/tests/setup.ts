/**
 * Vitest setup file for Nuxt/Vue tests.
 *
 * This file is run before each test file.
 */

import { config } from "@vue/test-utils";

// Mock Nuxt composables that are commonly used
// These can be overridden in individual tests

// Mock useRuntimeConfig
vi.mock("#app", () => ({
  useRuntimeConfig: () => ({
    public: {
      apiBase: "http://localhost:8500",
    },
  }),
  useNuxtApp: () => ({
    $api: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    },
  }),
  navigateTo: vi.fn(),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useRoute: () => ({
    path: "/",
    params: {},
    query: {},
  }),
}));

// Mock vue-sonner toast
vi.mock("vue-sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

// Global Vue Test Utils configuration
config.global.stubs = {
  // Stub router-link and nuxt-link
  NuxtLink: true,
  RouterLink: true,
  // Stub client-only to just render its content
  ClientOnly: {
    template: "<slot />",
  },
};
