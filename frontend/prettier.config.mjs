/**
 * Prettier configuration
 * @see https://prettier.io/docs/en/configuration.html
 */
export default {
  // Line length - match Nuxt/Vue community standards
  printWidth: 100,

  // Use 2 spaces for indentation (standard for Vue/Nuxt)
  tabWidth: 2,
  useTabs: false,

  // Use semicolons at the end of statements
  semi: true,

  // Use double quotes (consistent with Vue SFC templates)
  singleQuote: false,

  // Use single quotes in JSX
  jsxSingleQuote: false,

  // Trailing commas where valid in ES5 (objects, arrays, etc.)
  trailingComma: "es5",

  // Spaces between brackets in object literals
  bracketSpacing: true,

  // Put the > of a multi-line HTML element at the end of the last line
  bracketSameLine: false,

  // Arrow function parentheses: always include
  arrowParens: "always",

  // Prose wrapping for markdown
  proseWrap: "preserve",

  // HTML whitespace sensitivity
  htmlWhitespaceSensitivity: "css",

  // Vue-specific: indent script and style tags
  vueIndentScriptAndStyle: false,

  // End of line - LF for cross-platform consistency
  endOfLine: "lf",

  // Embedded language formatting
  embeddedLanguageFormatting: "auto",

  // Single attribute per line in HTML/Vue (better for diffs)
  singleAttributePerLine: false,

  // Plugins
  plugins: ["prettier-plugin-tailwindcss"],

  // Tailwind CSS plugin options
  tailwindFunctions: ["clsx", "cn", "cva"],
};
