// @ts-check
import pluginVue from "eslint-plugin-vue";
import vueTsEslintConfig from "@vue/eslint-config-typescript";
import globals from "globals";

/**
 * ESLint flat config for Nuxt/Vue 3 with TypeScript
 * @see https://eslint.org/docs/latest/use/configure/configuration-files
 */
export default [
  // ==========================================================================
  // Global settings and ignores
  // ==========================================================================
  {
    name: "global/ignores",
    ignores: [
      // Build outputs
      "**/dist/**",
      "**/.nuxt/**",
      "**/.output/**",
      "**/.nitro/**",

      // Dependencies
      "**/node_modules/**",

      // Cache directories
      "**/.eslintcache",
      "**/.cache/**",

      // Generated files
      "**/*.generated.*",
      "**/auto-imports.d.ts",
      "**/components.d.ts",
      "**/.nuxt/types/**",

      // Lock files
      "pnpm-lock.yaml",
      "package-lock.json",
      "yarn.lock",
    ],
  },

  // ==========================================================================
  // JavaScript/TypeScript base configuration
  // ==========================================================================
  {
    name: "global/javascript",
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2024,
      },
    },
    rules: {
      // Best practices
      "no-console": ["warn", { allow: ["warn", "error", "info"] }],
      "no-debugger": "warn",
      "no-alert": "warn",
      "no-unused-vars": "off", // Handled by TypeScript

      // ES6+ features
      "prefer-const": "error",
      "no-var": "error",
      "object-shorthand": "error",
      "prefer-template": "error",
      "prefer-arrow-callback": "error",

      // Code quality
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-implicit-coercion": "error",
      "no-return-await": "error",
    },
  },

  // ==========================================================================
  // Vue.js configuration
  // ==========================================================================
  ...pluginVue.configs["flat/recommended"],

  {
    name: "vue/custom-rules",
    files: ["**/*.vue"],
    rules: {
      // Vue 3 best practices
      "vue/multi-word-component-names": "off", // Nuxt uses single-word for pages
      "vue/no-v-html": "warn",
      "vue/require-default-prop": "off", // Not needed with TypeScript
      "vue/require-prop-types": "off", // TypeScript handles this
      "vue/no-unused-vars": "error",

      // Component organization
      "vue/block-order": ["error", { order: ["script", "template", "style"] }],

      // Template best practices
      "vue/html-self-closing": [
        "error",
        {
          html: { void: "always", normal: "always", component: "always" },
          svg: "always",
          math: "always",
        },
      ],
      "vue/padding-line-between-blocks": "error",
      "vue/no-empty-component-block": "error",

      // Composition API
      "vue/define-macros-order": [
        "error",
        { order: ["defineOptions", "defineProps", "defineEmits", "defineSlots"] },
      ],

      // Accessibility
      "vue/no-static-inline-styles": "warn",

      // Consistency
      "vue/component-name-in-template-casing": ["error", "PascalCase"],
      "vue/custom-event-name-casing": ["error", "camelCase"],
      "vue/define-emits-declaration": ["error", "type-based"],
      "vue/define-props-declaration": ["error", "type-based"],

      // Performance
      "vue/no-v-text-v-html-on-component": "error",
      "vue/prefer-true-attribute-shorthand": "error",
    },
  },

  // ==========================================================================
  // TypeScript configuration
  // ==========================================================================
  ...vueTsEslintConfig(),

  {
    name: "typescript/custom-rules",
    files: ["**/*.ts", "**/*.tsx", "**/*.vue"],
    rules: {
      // TypeScript specific
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/explicit-function-return-type": "off",
      "@typescript-eslint/explicit-module-boundary-types": "off",
      "@typescript-eslint/no-non-null-assertion": "warn",
      "@typescript-eslint/consistent-type-imports": "off", // Requires type information
      "@typescript-eslint/no-import-type-side-effects": "off", // Requires type information
    },
  },

  // ==========================================================================
  // Nuxt auto-imports (global variables)
  // ==========================================================================
  {
    name: "nuxt/globals",
    languageOptions: {
      globals: {
        // Nuxt composables
        definePageMeta: "readonly",
        defineNuxtConfig: "readonly",
        defineNuxtPlugin: "readonly",
        defineNuxtRouteMiddleware: "readonly",
        defineEventHandler: "readonly",
        defineNitroPlugin: "readonly",
        useRuntimeConfig: "readonly",
        useAppConfig: "readonly",
        useNuxtApp: "readonly",
        useHead: "readonly",
        useSeoMeta: "readonly",
        useRoute: "readonly",
        useRouter: "readonly",
        useFetch: "readonly",
        useLazyFetch: "readonly",
        useAsyncData: "readonly",
        useLazyAsyncData: "readonly",
        useState: "readonly",
        useCookie: "readonly",
        useError: "readonly",
        clearError: "readonly",
        createError: "readonly",
        showError: "readonly",
        navigateTo: "readonly",
        abortNavigation: "readonly",
        refreshNuxtData: "readonly",
        clearNuxtData: "readonly",
        setPageLayout: "readonly",
        setResponseStatus: "readonly",
        prerenderRoutes: "readonly",
        addRouteMiddleware: "readonly",

        // Vue
        ref: "readonly",
        reactive: "readonly",
        computed: "readonly",
        watch: "readonly",
        watchEffect: "readonly",
        onMounted: "readonly",
        onUnmounted: "readonly",
        onBeforeMount: "readonly",
        onBeforeUnmount: "readonly",
        nextTick: "readonly",
        toRef: "readonly",
        toRefs: "readonly",
        unref: "readonly",
        isRef: "readonly",
        shallowRef: "readonly",
        triggerRef: "readonly",
        customRef: "readonly",
        provide: "readonly",
        inject: "readonly",
        defineComponent: "readonly",
        defineAsyncComponent: "readonly",
        defineProps: "readonly",
        defineEmits: "readonly",
        defineExpose: "readonly",
        defineSlots: "readonly",
        defineOptions: "readonly",
        defineModel: "readonly",
        withDefaults: "readonly",

        // i18n
        useI18n: "readonly",
        useLocalePath: "readonly",
        useSwitchLocalePath: "readonly",

        // Pinia
        defineStore: "readonly",
        storeToRefs: "readonly",

        // $fetch
        $fetch: "readonly",
      },
    },
  },
];
