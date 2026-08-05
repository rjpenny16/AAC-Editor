const globals = require("globals");

/**
 * The frontend ships as plain files with no build step, so this config exists
 * to catch real mistakes — undeclared globals, unused bindings, accidental
 * fallthrough — rather than to enforce style. Formatting is Prettier's job.
 */
module.exports = [
  {
    ignores: ["node_modules/**", "test-results/**", "playwright-report/**"],
  },
  {
    // The editor frontend: browser globals, native ES modules, no bundler.
    files: ["tdsnap/web/static/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: globals.browser,
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-undef": "error",
      "no-var": "error",
      "prefer-const": "error",
      eqeqeq: ["error", "smart"],
      "no-fallthrough": "error",
      // An empty catch hides exactly the failures this app needs to surface.
      // Comment the block if the silence is deliberate.
      "no-empty": ["error", { allowEmptyCatch: false }],
    },
  },
  {
    // Playwright specs and Node-side config run under CommonJS. Specs also
    // reference browser globals inside page.evaluate() callbacks, which are
    // serialized and run in the page rather than in Node.
    files: ["tests/**/*.spec.js", "*.config.js", "eslint.config.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-undef": "error",
    },
  },
];
