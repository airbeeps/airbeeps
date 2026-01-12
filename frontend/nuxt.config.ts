// https://nuxt.com/docs/api/configuration/nuxt-config

import tailwindcss from "@tailwindcss/vite";

const appName = process.env.AIRBEEPS_APP_NAME || "Airbeeps";
const apiBaseUrl = process.env.AIRBEEPS_API_BASE_URL || "http://localhost:8500/api";
const enableOAuth = process.env.AIRBEEPS_ENABLE_OAUTH_PROVIDERS;

export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  devtools: { enabled: false },
  telemetry: false,
  ssr: false,
  css: ["~/assets/css/tailwind.css", "katex/dist/katex.min.css"],
  vite: {
    plugins: [tailwindcss()],
    optimizeDeps: {
      // Pre-optimize heavy dependencies to avoid re-optimization during navigation
      include: [
        // Markdown rendering (used in chat messages)
        "markdown-it",
        "markdown-it-texmath",
        "highlight.js",
        "katex",

        // PDF viewer (used in knowledge base)
        "pdfjs-dist",

        // Charts (used in admin analytics)
        "@unovis/ts",
        "@unovis/vue",

        // Tables (used in admin pages)
        "@tanstack/vue-table",

        // Form validation
        "vee-validate",
        "@vee-validate/zod",
        "zod",

        // UI components
        "lucide-vue-next",
        "reka-ui",
        "vue-sonner",

        // Utilities
        "class-variance-authority",
        "clsx",
        "tailwind-merge",
        "@vueuse/core",
        "path-to-regexp",
      ],
      // Exclude @nuxt/content internal dependencies (handled by the module itself)
      exclude: ["@nuxtjs/mdc"],
    },
  },

  app: {
    head: {
      title: appName,
    },
  },

  runtimeConfig: {
    public: {
      appName,
      appVersion: "0.0.0", // overridden by NUXT_PUBLIC_APP_VERSION
      apiBaseUrl,
      enableOAuthProviders: enableOAuth !== "false",
    },
  },

  modules: [
    "shadcn-nuxt",
    "@pinia/nuxt",
    "@nuxtjs/i18n",
    "@nuxtjs/color-mode",
    "@nuxt/scripts",
    "@nuxt/content",
  ],

  content: {
    experimental: { sqliteConnector: "native" },
  },

  colorMode: {
    classSuffix: "",
  },

  shadcn: {
    /**
     * Prefix for all the imported component
     */
    prefix: "",
    /**
     * Directory that the component lives in.
     * @default "./components/ui"
     */
    componentDir: "./app/components/ui",
  },

  nitro: {
    devProxy: {
      "/api": {
        target: apiBaseUrl,
        changeOrigin: true,
      },
    },
  },

  i18n: {
    defaultLocale: "en",
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: "i18n_redirected",
      redirectOn: "root", // recommended
    },
    strategy: "no_prefix",
    locales: [{ code: "en", name: "English", language: "en-US", file: "en.ts" }],
  },
});
