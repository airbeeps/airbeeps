import { defineVitestConfig } from "@nuxt/test-utils/config";

export default defineVitestConfig({
  test: {
    // Use happy-dom for faster tests
    environment: "happy-dom",

    // Test file patterns
    include: ["tests/unit/**/*.{test,spec}.{js,ts,vue}"],

    // Global test timeout
    testTimeout: 10000,

    // Enable globals (describe, it, expect)
    globals: true,

    // Coverage configuration
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      include: ["app/**/*.{ts,vue}"],
      exclude: [
        "app/components/ui/**", // Exclude shadcn-vue UI components
        "**/*.d.ts",
        "**/node_modules/**",
      ],
    },

    // Setup files
    setupFiles: ["./tests/setup.ts"],
  },
});
