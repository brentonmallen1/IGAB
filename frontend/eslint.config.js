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
  // 22 set-state-in-effect, 6 refs, 2 exhaustive-deps, 1 rules-of-hooks.
  // rules-of-hooks (PayeesPage: a conditional useMemo) is a real correctness
  // risk and worth fixing on its own; it is not this pass's subject.
  'react-hooks/set-state-in-effect': 'warn',
  'react-hooks/refs': 'warn',
  'react-hooks/exhaustive-deps': 'warn',
  'react-hooks/rules-of-hooks': 'warn',
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
])
