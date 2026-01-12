/**
 * Pre-import heavy dependencies to ensure Vite optimizes them at startup
 * This plugin runs before all others (00. prefix) to trigger optimization early
 *
 * These imports are tree-shaken in production, so they don't add to bundle size
 * They just help Vite discover dependencies during development
 */
export default defineNuxtPlugin({
  name: "vite-deps-preload",
  parallel: true,
  setup() {
    if (import.meta.dev) {
      // These dynamic imports trigger Vite's dependency optimization
      // but don't actually load the modules (lazy loading)
      import("markdown-it").catch(() => {});
      import("highlight.js").catch(() => {});
      import("katex").catch(() => {});
      import("pdfjs-dist").catch(() => {});
      import("@unovis/vue").catch(() => {});
      import("@tanstack/vue-table").catch(() => {});
    }
  },
});
