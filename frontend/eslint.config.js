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

/**
 * `ChartTooltip` used to default its `formatter` to a hard-coded
 * ``$${v.toLocaleString('en-US', ...)}``. Eighteen of its nineteen call sites
 * passed nothing and so inherited three bugs each: the budget's currency and
 * number format ignored, privacy mode defeated (its purpose is that "sign and
 * digits hidden, so overspending can't be inferred"), and — on the two charts
 * whose series are not money — a percentage and a month count rendered as
 * dollars.
 *
 * The default is gone and the prop is required, so TypeScript already catches
 * a missing one. This says why, in the error, at the moment someone reaches
 * for a default again.
 */
const NO_UNFORMATTED_CHART_TOOLTIP = {
  selector: "JSXOpeningElement[name.name='ChartTooltip']:not(:has(JSXAttribute[name.name='formatter']))",
  message:
    'ChartTooltip needs an explicit formatter. Pass formatMoney from useFormatters() for money ' +
    '(it honours currency, number format and privacy mode), or a unit-specific formatter for ' +
    'anything that is not money — a percentage or a month count rendered as dollars is the bug ' +
    'the old default caused.',
}

/**
 * A numeric chart axis with no `tickFormatter` prints raw numbers: no
 * currency, no number format and, above all, no privacy mask. The Emergency
 * Fund chart's money axis shipped that way beside a masked tooltip and masked
 * cards, so its gridlines read the fund to within one line while every figure
 * on the page said $••••. Spread `useMoneyAxis()` for money — it carries the
 * formatter and the phone width — or pass a formatter for the axis's own unit.
 * A category axis prints names and is exempt; recharts' XAxis is a category
 * axis unless it says `type="number"`.
 */
const NO_UNFORMATTED_NUMERIC_AXIS = [
  {
    selector:
      "JSXOpeningElement[name.name='YAxis']:not(:has(JSXAttribute[name.name='tickFormatter'])):not(:has(JSXSpreadAttribute)):not(:has(JSXAttribute[name.name='type'][value.value='category']))",
    message:
      'A numeric YAxis needs a tickFormatter. Spread useMoneyAxis() for money (currency, number ' +
      'format and privacy mode), or pass a formatter for the axis’s own unit.',
  },
  {
    selector:
      "JSXOpeningElement[name.name='XAxis']:has(JSXAttribute[name.name='type'][value.value='number']):not(:has(JSXAttribute[name.name='tickFormatter'])):not(:has(JSXSpreadAttribute))",
    message:
      'A numeric XAxis needs a tickFormatter. Pass useMoneyAxis().tickFormatter for money, or a ' +
      'formatter for the axis’s own unit.',
  },
]

/**
 * `toISOString()` is UTC, so slicing a date out of it names the wrong day for
 * most of the world for part of every day: tomorrow every evening west of
 * Greenwich, yesterday after midnight east of it. The AI chat told the server
 * it was tomorrow every night after 8 in New York; an opening balance left
 * undated was booked a day late; a test computing "today" this way failed
 * every evening. Applied to tests too, for that last reason.
 */
const NO_UTC_DATE_SLICE = {
  selector:
    "CallExpression[callee.property.name='slice'][callee.object.callee.property.name='toISOString']",
  message:
    'toISOString() is UTC: sliced to a date it is tomorrow every evening west of Greenwich. Use ' +
    'toISODate(d), today() or currentMonthStart() from utils/dates.',
}

/**
 * Overlay geometry has now been consolidated twice. The first round collapsed
 * five copies into `utils/anchoredPosition.ts`; by the second, three more
 * surfaces were again running off the bottom of the screen — ContextMenu
 * clamping against `const menuHeight = 280`, two callers subtracting a magic
 * 160 from their anchor, and a tooltip with its own EDGE constant, its own
 * clamp and its own flip.
 *
 * Every one of those started with a component measuring the window for itself.
 * So that is what is banned: read the viewport and the trigger through
 * `useAnchoredPosition`, which measures the VISUAL viewport (a raised keyboard
 * shrinks it and leaves `innerHeight` unchanged) and the panel's real height.
 *
 * Scoped to the two modules that own the rule plus `useAppViewport`, which
 * publishes the insets everything else reads as CSS custom properties.
 */
const NO_HAND_ROLLED_VIEWPORT_MATH = [
  {
    selector: "MemberExpression[property.name='getBoundingClientRect']",
    message:
      'Measuring a trigger by hand is how overlays end up off-screen. Use useAnchoredPosition ' +
      '(hooks/useAnchoredPosition.ts) — it measures the trigger, the panel and the visual viewport.',
  },
  {
    selector:
      "MemberExpression[object.name='window'][property.name=/^inner(Width|Height)$/]",
    message:
      'window.innerHeight is the LAYOUT viewport: on iOS a raised keyboard leaves it unchanged, ' +
      'so a panel sized to it opens under the keyboard. Use useAnchoredPosition, or the ' +
      '--vvh / --vv-bottom custom properties useAppViewport publishes.',
  },
]

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
      'no-restricted-syntax': [
        'error',
        NO_BARE_PARSE_FLOAT,
        NO_UNFORMATTED_CHART_TOOLTIP,
        ...NO_UNFORMATTED_NUMERIC_AXIS,
        NO_UTC_DATE_SLICE,
        ...NO_HAND_ROLLED_VIEWPORT_MATH,
      ],
    },
  },
  {
    // The money layer itself. These are the implementations the rule points
    // at, and `utils/searchParser.ts` parses a search grammar rather than an
    // amount to store.
    files: ['src/utils/money.ts', 'src/utils/amountExpression.ts', 'src/utils/searchParser.ts'],
    rules: { 'no-restricted-syntax': ['error', NO_UTC_DATE_SLICE, ...NO_HAND_ROLLED_VIEWPORT_MATH] },
  },
  {
    // The geometry rule's own home, and the hook that publishes the viewport
    // insets it reads. These are the implementations the ban points at.
    //
    // Beside them, four files that measure an element for something that is
    // not overlay placement — the ban is about *anchoring a floating panel*,
    // and these have no panel:
    //   useMeasuredHeight  offsets one sticky row by the height of another,
    //                      which is the one thing CSS cannot express.
    //   useChartHeight     caps a chart on short phones; charts are not
    //                      re-measured on keyboard show/hide, so the layout
    //                      viewport is the right one and its comment says so.
    //   RoadmapMap         converts a wheel event to a point inside a
    //                      pan/zoom canvas.
    //   TransactionTable   computes the virtualiser's scroll margin.
    //   useViewportDiagnostics reads every raw viewport number to DISPLAY it
    //                      on Settings → Mobile; it positions nothing.
    files: [
      'src/hooks/useAnchoredPosition.ts',
      'src/hooks/useAppViewport.ts',
      'src/hooks/useViewportDiagnostics.ts',
      'src/hooks/useMeasuredHeight.ts',
      'src/hooks/useChartHeight.ts',
      'src/components/guide/RoadmapMap.tsx',
      'src/components/transactions/TransactionTable/TransactionTable.tsx',
    ],
    rules: { 'no-restricted-syntax': ['error', NO_BARE_PARSE_FLOAT, NO_UTC_DATE_SLICE] },
  },
  {
    // Tests stub the viewport to state a case; that is the point of them.
    files: ['**/*.test.ts', '**/*.test.tsx'],
    rules: { 'no-restricted-syntax': ['error', NO_BARE_PARSE_FLOAT, NO_UTC_DATE_SLICE] },
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
