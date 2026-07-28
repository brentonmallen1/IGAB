# IGAB Feature Checklist

Track implementation progress here. Add new items to Backlog as they come up.

_Reconciled 2026-07-21 after the financial-correctness audit (commit 540c2ac)._

---

## Cutover blockers (do before/while replacing YNAB)

- [x] YNAB import: account-type mapping step (preview endpoint + Review Accounts step on the budget selector with name-based type suggestions)
- [x] Code backup: pushed to private remote github.com/brentonmallen1/IGAB
- [ ] Execute cutover per README.md (fresh DB → import → double sync → integrity green → parallel-run one statement cycle)

---

## Phase 3: Polish & PWA

### Advanced Accounts
- [x] Loan accounts with amortization schedule (2026-07-25: delivered via R7-R9 liabilities — a Liability links an account or is manually tracked; 2026-07-26: renamed debt→liability throughout)
- [x] Interest calculation (2026-07-25: cent-exact amortization engine in `amortization.py`)
- [x] Extra payment simulation (2026-07-25: what-if `?extra_payment=` overlay on the liability page with months/interest saved)

### PWA
_Scope decision 2026-07-22: the app is network-required — no offline data. PWA = installable + app-shell precache + update prompt + explicit offline state. IndexedDB cache / sync queue / conflict resolution intentionally dropped._
- [x] App manifest (installable, icons derived from favicon.svg)
- [x] Service worker (app-shell precache, prompt-style updates via toast)
- [x] Offline/unreachable-server banner
- [x] Production profile serves real static build (multi-stage Dockerfile → nginx, cache headers, relative API base)
- ~~IndexedDB offline cache~~ (dropped — network-required by design)
- ~~Sync queue for offline mutations~~ (dropped)
- ~~Conflict resolution strategy~~ (dropped)

### Mobile UX
- [x] Bottom tab bar + bottom-sheet primitives (replaces drawer on phones; BottomSheet/SelectionSheet in common/, Android-back dismissal)
- [x] Budget page mobile card layout + inspector/move-money sheets (rename/hide/delete moved into inspector sheet on touch)
- [x] Transactions mobile cards + full-screen editor + long-press select (inline cell editing stays desktop-only)
- [x] Quick-add sheet (center ＋: amount-first entry, payee-memory category prefill, save-and-add-another)
- [x] Receipt camera capture (attach in quick-add + Take Photo in attachment panel; pillow-heif fixes real HEIC uploads)
- [x] Payee proximity suggestions — opt-in per-device setting, foreground-only; lat/lng on transactions (migration 0002), `GET /{budget}/payees/nearby` (bounding box + haversine), "Nearby" section in quick-add payee picker
- [x] Deeper mobile polish backlog: chart touch interactions (already have tap-to-drill on 11 charts), pinch-zoom in lightbox (usePinchZoom hook, double-tap reset), month-swipe on budget (useSwipeNavigation hook)

---

## Phase 4: Planning
- [ ] What-if scenarios
- [ ] Loan calculators
- [ ] simulations

---

## Backlog

_Add items here as they come up during development._

### Budget page money movement (YNAB-parity cluster) — completed 2026-07-22
- [x] Move money to/from a category (API endpoint + click-the-available popover, TBA both directions, budget_moves history table + per-month endpoint)
- [x] Auto distribute ready-to-assign funds to cover overspent categories (`cover-overspent/preview` + `apply` mirroring fill-targets; round-down distribution so proposals never exceed TBA; apply revalidates against fresh balances and routes through move_money for the audit trail)
- [x] Total overspent display (`total_overspent` on the months endpoint + hero chip)
- [x] TBA money up and center (YNAB-style hero pill with split Assign button, overspent chip, drawer with cover action; BottomSheet drawer on mobile)
- [x] Move-history view beyond the popover (full month log in the hero drawer)
- [x] YNAB-style Assign dropdown on the TBA hero (2026-07-25: Auto tab with per-strategy preview amounts — underfunded, assigned/spent last month, averages, reset available/assigned — each opening a signed-delta preview modal before apply; Manually tab assigning from TBA to one category; apply recomputes server-side and routes through move_money for the audit trail; replaced legacy fill-targets modal/endpoints; fixed pre-existing get_category_history end_date bug that zeroed last-month/average spent)

### UI / UX
- [x] Polish pass round 1 (2026-07-22) — TBA hero, budget selector card layout (whole-card open, Current badge, overflow menu, two-column with create/import demoted), Settings reorganized (anchor deep links, integrity + backups surfaced above integrations), typography (font-size tokens incl. 2xs/display, weight tokens, tabular-nums on budget money cells, shared `.section-label` + `.kbd` utilities)
- [x] Command palette (cmdk, ⌘K + header palette bar; navigation incl. accounts/views, add transaction, auto-assign, cover overspending, move money, month jump, theme switch, integrity/backups deep links, live payee + transaction search via new `search` param on budget-wide transactions endpoint; desktop-only)
- [x] Real keyboard shortcuts (`?` help overlay from a single source of truth in `keyboard/shortcuts.ts`; `[`/`]`/`T` month nav, Shift+D duplicate, Shift+T repeat, Delete on selection sharing the context-menu handlers; Cmd+Z migrated into the registry)
- [x] Polish pass round 2 — remaining layout modernization sweeps (reports, account register aesthetics): `.ms-auto`/`.flex-row` utilities in base.css, `.report-section__header` wrapper, inline style cleanup across 20 report components, AccountPage header class
- [x] Palette follow-ups: scroll-to/highlight transaction on account page from search result (`?highlight=` param + 2s fade animation); payee result filters the payees page (`?q=` param)
- [ ] Custom reminder notifications (pay bills, etc.)
- [ ] Explicit "set as default category" affordance on payees (memory now learns once and never overwrites; changing the default is only possible via the payee edit form)

### Payees
- [ ] Auto-suggest merges via rapidfuzz — merge wizard with final review before commit
- [ ] Payee list: sort, filter/search, column alignment

### Transactions
- [x] Split transaction button always accessible (outside scroll area), opens modal
- [x] Split transaction "add remaining to category" button

### Data
- [x] Generate sample budget (2026-07-25: one-click card on the budget selector + `just sample-budget <email>` CLI; 12 months of curated data — 5 account types, splits, transfers, targets, tags, scheduled, reconciliation; generator derives assignments from the data and sweeps surplus into Emergency Fund so TBA lands exactly at $150 with only Dining Out overspent, for any anchor date; integrity green, 7 integration tests)
- [ ] Auto backups configurable in UI (daily backup container + retention exist via env vars; frequency/count/age settings do not)
- [ ] YNAB-compatible export (exit strategy — a system of record needs a way out too)
- [ ] Attachment file GC (files of long-deleted transactions are never removed from disk)

### Accounts & Finance Tools
- [ ] Savings tools section (personal finance flowchart, savings guidance)
- [ ] Education section (personal finance flowchart, other resources)
- [ ] Migrating to a new budget plan (preserve transaction history)
- [ ] Monthly category balance snapshots (O(1) budget summary, invalidate on change) — summary currently recomputes month-by-month per category; fine today, will crawl after years of data
- [ ] Budget lookback / month comparison (side-by-side via snapshots)

### Testing & CI
- [ ] CI on push (GitHub Actions: `just quality` + backend suite with a Postgres service container + `npm run typecheck`) — deferred while development is active; run the suite manually before commits meanwhile
- [ ] Frontend tests for money-critical components (transaction editor, split editor cents math, bulk flows) — backend has 559 tests incl. real-DB integration; frontend has only searchParser tests

### Localization
- [ ] Settings for currency, decimal vs comma separator, date format (CSV import now handles EU separators exactly; UI display settings remain)
- [ ] All numbers rounded to 2 decimal places throughout app

### Future Reports — full designs (backend + UX + test plans) in docs/future-reports-roadmap.md
- [x] R1 Tags foundation: tags/joins schema, system tags, TagChip + theme color slots, Settings management, inspector + payee pickers, bulk tagging (M)
- [x] R2 Tag-aware report semantics (2026-07-26: Hide Savings toggle in Pareto/Treemap excludes savings/long_term_expense-tagged categories; Savings report in Financial State group)
- [x] R3 Subscriptions report (2026-07-26: payee-tagged subscriptions aggregated in Spending group — stacked bar chart, metrics, table; auto-detection deferred to backlog)
- [x] R4 Anomaly detection (2026-07-26: z-score outliers with leave-one-out baseline, guard rails; Anomalies tab in Insights with sensitivity toggle, % change display, sparklines, drill-down)
- [x] R5 Payday-effect panel (2026-07-26: second panel in Day Patterns — bar chart of avg daily spend for N days after income events vs baseline; excludes subscriptions)
- [x] R6 Cash projection fan chart (2026-07-26: Projection tab in Cash Flow — bootstrap 500 paths from weekday-bucketed historical flows + scheduled transactions + subscription patterns; P10/25/50/75/90 bands, deterministic line, upcoming events list, goes-negative warning)
- [x] R7 Liability data model + amortization engine (2026-07-25: migration 0004 — Liability + LiabilityBalanceSnapshot + Category.linked_liability_id; cent-exact `amortization.py`; LiabilityService with three payment-derivation paths + live payoff projection; full CRUD/snapshot/amortization/link-liability API; unmanaged liabilities join net worth exactly once in BOTH computations; 2026-07-26: renamed debt→liability; squashed migrations to single 0001_initial.py)
- [x] R8 Liabilities sidebar section + per-liability detail page (2026-07-25: sidebar group with Link2/PenLine mode icons, LiabilitiesOverviewPage cards + account suggestions, LiabilityPage with 4-state payoff pill, Now/Beginning paydown chart with what-if overlay, show-more amortization table, update-balance + link-category flows; 2026-07-26: account classification (asset/liability) for tracking accounts — sidebar now groups by Assets/Liabilities instead of generic Tracking; liability tracker becomes optional enhancement on liability-classified accounts)
- [x] R9 Consolidated Liabilities report tab (2026-07-25: Liabilities tab in Financial State — rollup metrics, stacked per-liability balance area, type/mode filters, sortable table with row-click to detail page)
- [x] Sample budget generates liabilities (2026-07-26: Car Loan managed + Dental Payment Plan unmanaged with snapshots)
- [x] Reports navigation UX (2026-07-26: group dropdown + horizontal tabs replaces scrolling tab bar; unsupported filters hidden instead of dimmed)
- Deferred: inflation-adjusted trends, "if invested instead" — need external_series infra (sketched in roadmap)
- Deferred: R3 auto-detection — cadence detection algorithm, confidence scoring, "suggest tags" UI

### Other
- [x] Locale/format settings — per-budget number format (1,234.56 vs 1.234,56 vs 1 234,56), date format (M/D/Y vs D/M/Y vs Y-M-D), time format (12h vs 24h) — Settings page UI + app-wide FormatContext
- [ ] 2FA (TOTP) support
- [ ] Budget notes / annotations
- [ ] Transaction flags / colors
- [ ] Multi-currency support (transactions in foreign currencies)
- [ ] Plugin framework + plugin management page
- [ ] Mock SimpleFIN API for dev (a FakeClient exists in the integration tests; a dev-mode mock server with generated timestamps does not)
- [ ] Budgeted-mode sankey ignores account filters (pre-existing backend inconsistency; spent mode honors them — compare mode inherits it)

---

## Completed

### Financial Correctness Audit (2026-07-21, commit 540c2ac)
- [x] Real-Postgres integration test suite (546 backend tests, money-conservation invariant checker, hand-computed dollar assertions)
- [x] Split transactions flow into category activity, budget available, and all reports (leaf-row aggregation rules in `txn_filters.py`)
- [x] Pending transactions excluded from every money aggregate (TBA never skews on bank auths)
- [x] Sync dedup: accepted matches keep sync_id (no re-import loop); pending→posted adopts bank amount/date with `entered_date` provenance; unique DB dedup indexes; stale-pending sweep
- [x] Invariant guards: transfer pairs as a unit, split integrity, reconciled lifecycle (finish auto-adjustment + unreconcile endpoint/UI), merge amount-equality + attachment reassignment
- [x] Bulk endpoints report per-item failures (frontend toasts)
- [x] Scheduled transfers create both legs
- [x] YNAB import fully idempotent including transfers, per-leg cleared preserved
- [x] Exact string→Decimal CSV parsing; NaN/scale/bounds Money validation on all amount inputs; UTC clock
- [x] Ownership scoping on all ~100 API endpoints (two-user 404 tests)
- [x] Categorized transfers to off-budget accounts count as spending (YNAB semantics)
- [x] Live integrity check (Settings → Data Integrity + `GET /budgets/{id}/integrity`)
- [x] Backups: `just backup` / `just restore` (restore exercised), daily backup container in production profile
- [x] Frontend: cents-integer money math, split-editor duplication bug fixed, typecheck restored and clean

### Reconciliation (completed during audit)
- [x] Statement matching workflow
- [x] Lock reconciled transactions (+ explicit unreconcile)
- [x] Adjustment transaction (auto-created on statement mismatch)
- [x] Reconciliation history

### Integrations (completed during audit hardening)
- [x] SimpleFIN connection setup (beta-bridge.simplefin.org)
- [x] SimpleFIN account linking
- [x] SimpleFIN transaction sync (rate-limit aware: 12 req/day, 90-day first-sync window)
- [x] Deduplication for imported transactions (sync_id exact + fuzzy auto/review matching, cross-source)
- [x] Reports test coverage (integration tests for spending, income/expense, budget-vs-actual, sankey, dashboard)
- [x] Payee management page (view, edit, merge, bulk operations)
- [x] Multi-select merge with name selection and sanity check (transaction count preview)
- [x] Backups and exports (pg_dump backups; CSV/JSON transaction export)

### Phase 1: MVP

#### Infrastructure
- [x] Docker Compose setup (api, db, frontend)
- [x] PostgreSQL schema via Alembic migrations
- [x] Environment configuration (.env)
- [x] justfile commands (dev, build, migrate, test)
- [x] JWT authentication (single user)

#### Backend — Core CRUD
- [x] Budget CRUD
- [x] Account CRUD (checking, savings, credit card, loan, tracking)
- [x] Category group CRUD
- [x] Category CRUD
- [x] Payee CRUD

#### Backend — Transactions
- [x] Transaction create / read / update / delete
- [x] Transfer handling (paired transactions, no category)
- [x] Split transactions
- [x] Transaction search & filtering
- [x] Payee auto-categorization memory

#### Backend — Budgeting Engine
- [x] Category balance calculation (prior + assigned − activity)
- [x] To Be Assigned calculation
- [x] Monthly budget assignment
- [x] Overspending handling (visual warnings: overspent row highlight + budget banner)
- [x] Auto-assign rules (fill targets, proportional by underfunded % with preview)

#### Backend — Imports
- [x] CSV import (manual / bank export)
- [x] YNAB4 importer (.yfull file)

#### Frontend — Core
- [x] Dark mode default (+ light theme toggle)
- [x] All theme palettes built (gruvbox, catppuccin, rose-pine, nord)
- [x] App layout: sidebar, header, main content
- [x] Collapsible sidebar (icon-only mode when collapsed)
- [x] Account sidebar list
- [x] Budget view (category groups + category rows)
- [x] Inline category assignment editing
- [x] Account register (transaction list)
- [x] Transaction editor (create/edit form)
- [x] Transfer entry
- [x] Split transaction entry
- [x] YNAB4 import page
- [x] CSV import page
- [x] Settings page (theme selector, account creation, budget creation)
- [x] Light/dark mode and color palette accessible at all times (header)
- [x] Uncategorized transactions — "Needs Category" warning pill
- [x] Transaction duplication (single row and bulk selection)

### Phase 2: Advanced Features

#### Goals & Targets
- [x] Needed-for-spending target
- [x] Savings balance target
- [x] Monthly funding target
- [x] Target status display (underfunded / funded)
- [x] Progress bar for funding status (expanded pill bar with %, amount remaining, monthly pace)
- [x] Monthly needed amount display for date-based savings goals
- [x] LED dot indicator in compressed row mode
- [x] Expired target detection (past target_date shows "expired" badge)
- [x] Past Targets section in inspector sidebar (view, edit to reuse, delete)

#### Scheduled Transactions
- [x] Recurring transaction rules (daily/weekly/monthly/yearly)
- [x] Auto-create vs reminder mode
- [x] Upcoming transaction projection (shown in account register)
- [x] Make repeating from transaction context menu
- [x] Payee column in scheduled transactions list

#### Themes
- [x] Gruvbox (dark + light)
- [x] Catppuccin (Mocha + Latte)
- [x] Rose Pine (+ Moon)
- [x] Nord

#### Reports — Completed
- [x] Drill-down transaction panels (2026-07-21: click a chart element → inline filtered transaction list below the chart; budget-wide `GET /{budget_id}/transactions` with leaf/parent scope + posted/cash-flow semantics so panel totals reconcile with chart values; wired on Pareto, Treemap, Budget vs Actual, Payees, Volatility, Seasonality cells, Day Patterns, Income vs Expenses bars, Sankey category/payee/income nodes, Timeline cards)
- [x] Export per report (CSV / JSON via papaparse + PNG via html-to-image with theme background; shared ReportExportButton on all 15 tabs; transaction-level export moved to Overview)
- [x] Multi-select searchable dropdowns for category / payee / account filters (plus per-tab filter support matrix — controls a report ignores are dimmed, not silently ineffective)
- [x] Spending treemap drill-down fixed (inverted guard in visibleItems; group → categories renders; category tiles open the transaction panel)
- [x] Sankey — previous-period comparison (Compare toggle fetches the preceding equal-length window; +/-$ and % deltas on nodes and tooltips, "new" badge, delta captions on metric cards)
- [x] Report infrastructure: tabbed navigation (Overview, Financial State, Cash Flow, Budget, Spending, Insights)
- [x] Shared filter bar with date range presets (This Month, Last Month, Last 3/6/12 Months, Last Year, Custom)
- [x] Global group-by filter (Group / Category) applied across Pareto, Treemap, Sankey
- [x] Info (i) button on each report with explanatory modal
- [x] Overview dashboard (TBA, net worth, burn rate, savings rate, days-to-zero, income/expenses this month, top categories)
- [x] Net worth over time (stacked area by account type)
- [x] Account composition chart (checking / savings / credit card / loan / tracking over time)
- [x] Income vs expenses (bars + net cash flow line)
- [x] Rolling 30/90 day burn rate
- [x] Cash flow Sankey — drill-down: Income → Groups → Categories → Payees; Spent/Budgeted toggle
- [x] Budget vs actual (horizontal bars, sort by overspent, tooltip shows group)
- [x] Cumulative variance (running budget drift line chart)
- [x] Category volatility (std dev bars with min/max)
- [x] Pareto analysis (sorted bars + cumulative % line, grouped by group/category)
- [x] Spending treemap (hierarchical, group/category mode)
- [x] Seasonality heatmap (months × categories)
- [x] Payee analysis (top payees with % of total, recurring detection, monthly trend)
- [x] Day-of-week spending patterns
- [x] Event timeline / large transactions (annotated, limit toggle)
- [x] Transaction export (CSV / JSON) from reports page



ideas:
- create a mock api for dev instead of calling the simplefin api, it calls this and returns a static set of data. though it would have to be generated for a relevant time stamp or something?


- receipt extraction into categories and then do a split transaction. need to figure out a way to decode some things, maybe need a upc database interactoin or something to try to decode things and figure out what the item was. maybe have a table per receipt that has a column for the original item string and then the upc actual object name

- receipts should be stored as a scan? or allow the phone to use the scan feature. this is to help with image sizes as well as potentially with ocr
- more account types like investment accounts, etc?

- need to have a means to have/handle credit cards / other budget accounts in the budget view. like a section for credit cards, savings, etc. kinda like how ynab handles them a bit. need to find an explanation of how it works and try to remember/articulate why it was confusing for me.

fixes:
- cappuchin light color palette, the text color in the sidebar is too dark / no contrast and hard to read
- pareto should indicate when the user's finances aren't adhearing to the idea. like yellow border around the % of cateogires with some commentary about what the user might want to do about it
- report chart hover/tooltips have bad color palettes and are hard to read. need to check each color palette option
-  budget item notes don't save or have a save button. 

todo:
- fable review/audit of all of the reports to make sure they calculate things correctly, have appropriate tests to make sure they do, and are displaying things correctly/effectively. also, making sure we're using recharts effectively and not making custom components, etc where they arent'y needed
- fable security audit - sql injection, etc.
- fable impeccable? style consistency throughout the application
- fable review the mobile interface. make sure the number pad shows up when clicking to add an amount, UI/UX for everything else when adding a transaction, as well as the ability to take a photo of the receipt
- fable audit/ review for common component usage and remove arbitrarily unique components
