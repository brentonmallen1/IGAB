import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

/**
 * `npm run lint` is a CI gate. It was `continue-on-error` against a red
 * baseline of 41 errors, which meant any rule added to it enforced nothing.
 *
 * Rather than block this on clearing that backlog, the two legacy families are
 * warnings — visible and counted, not fatal — and everything else is an error.
 * The warning count is the debt; it should go down, never up.
 */
const LEGACY_WARNINGS = {
  // 22 set-state-in-effect, 6 refs, 2 exhaustive-deps.
  //
  // rules-of-hooks is NOT among them: it is a correctness rule, not a style
  // one — a component whose hook count changes between renders is broken, not
  // untidy. Its single violation (PayeesPage guarded on budgetId above a
  // useMemo) is fixed, so it stays an error and cannot come back.
  'react-hooks/set-state-in-effect': 'warn',
  'react-hooks/refs': 'warn',
  'react-hooks/exhaustive-deps': 'warn',
  // 7 files export a helper beside a component; only affects Fast Refresh.
  'react-refresh/only-export-components': 'warn',
}

/**
 * `parseFloat` is correct for a canonical decimal string the server sent and
 * wrong for anything a person typed: `parseFloat("1,234.56")` is 1, and
 * `parseFloat("1.234,56")` is 1.234 — both separator conventions
 * `utils/money.ts` explicitly supports. Paired with `|| 0` it silently books
 * zero, which is how a recurring transaction and two target forms came to
 * write $0.00 for a typed amount they could not read.
 *
 * The rule's value is that it makes the author say which kind of string they
 * hold: `parseAmountInput` for a keystroke, `parseApiDecimal` for a server
 * value. It is deliberately not scoped away from the files that legitimately
 * parse server strings — those were given the named helper instead.
 *
 * `Number(...)` is not restricted: `Number(x ?? 0)` over server decimals is
 * everywhere and legitimate, so banning it would be pure noise.
 */
const NO_BARE_PARSE_FLOAT = {
  selector: "CallExpression[callee.name='parseFloat']",
  message:
    'parseFloat misreads typed amounts (1,234.56 → 1). Use parseAmountInput for user input, ' +
    'parseApiDecimal for canonical server strings (both in utils/money), or expressionToCents.',
}

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      ...LEGACY_WARNINGS,
      // Underscore-prefixed placeholders in test mocks are deliberate.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
      'no-restricted-syntax': ['error', NO_BARE_PARSE_FLOAT],
    },
  },
  {
    // The money layer itself. These are the implementations the rule points
    // at, and `utils/searchParser.ts` parses a search grammar rather than an
    // amount to store.
    files: ['src/utils/money.ts', 'src/utils/amountExpression.ts', 'src/utils/searchParser.ts'],
    rules: { 'no-restricted-syntax': 'off' },
  },
  {
    // ── Readability budget, .ts ONLY ────────────────────────────────────────
    // Deliberately not applied to .tsx. The `complexity` rule counts every
    // `&&` and ternary in JSX, so a component that renders a lot of optional
    // bits scores enormously without being hard to follow — CategoryRow.tsx
    // reads 76, TransactionEditor.tsx 172. Gating that would push JSX into
    // wrapper components to satisfy a number, which is churn, not clarity.
    // A .tsx file's real budget is its LENGTH, and that lives in
    // `scripts/check-size.py` alongside the Python one.
    //
    // On .ts — the pure modules where the rules actually live — the numbers
    // mean what they say, and there are only 11 violations across 6 files.
    files: ['src/**/*.ts'],
    ignores: ['**/*.test.ts'],
    rules: {
      complexity: ['error', 15],
      'max-lines-per-function': [
        'error',
        { max: 150, skipBlankLines: true, skipComments: true },
      ],
    },
  },
  {
    // The debt list for the block above — `warn`, following the same pattern
    // as LEGACY_WARNINGS: the count is the debt and should go down, never up.
    // searchParser.ts is six of the eleven on its own; it parses a search
    // grammar, and a hand-written parser is the one place a high branch count
    // is the honest shape rather than a mess.
    files: [
      'src/utils/searchParser.ts',
      'src/api/transactions.ts',
      'src/components/guide/flowLayout.ts',
      'src/components/guide/tools/payoffRows.ts',
      'src/components/reports/charts/sankeyView.ts',
      'src/stores/uiStore.ts',
    ],
    rules: {
      complexity: ['warn', 15],
      'max-lines-per-function': [
        'warn',
        { max: 150, skipBlankLines: true, skipComments: true },
      ],
    },
  },
])
