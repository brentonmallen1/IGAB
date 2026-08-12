# IGAB Feature Checklist

Track implementation progress here. Add new items to Backlog as they come up.

_Reconciled 2026-07-21 after the financial-correctness audit (commit 540c2ac)._

---

## Cutover blockers (do before/while replacing YNAB)

- [x] YNAB import: account-type mapping step (preview endpoint + Review Accounts step on the budget selector with name-based type suggestions)
- [x] Code backup: pushed to private remote github.com/brentonmallen1/IGAB
- [ ] Execute cutover per README.md (fresh DB → import → double sync → integrity green → parallel-run one statement cycle) — 2026-08-10: will run on the Unraid host after budgero Phase B4 (packaging) rather than locally

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
- [ ] Custom reminder notifications (pay bills, etc.) — deferred
- [x] Auto-categorization: uses most recent category for payee (2026-07-28) — replaces static `default_category_id` learning; adapts automatically as categorization patterns change; `default_category_id` preserved as fallback for new payees with no history

### Payees
- [x] Auto-suggest merges via rapidfuzz — "Find Duplicates" button with sensitivity picker (loose/balanced/strict), merge wizard with final review before commit; AI Cleanup disabled when Ollama unavailable
- [x] Payee list: sortable Name/Transactions columns, search includes mapping_samples, tabular-nums alignment
- [x] Regex match patterns (2026-08-02): `match_pattern` on payees (migration 7c2a9d41e5b3) applied to incoming raw names — exact > regex > fuzzy precedence in transaction create/sync and CSV import batch; merge modal suggests a pattern generalized from the selected names (common prefix/suffix, token-boundary safe) with live match preview; editable inline on the payees page

### Transactions
- [x] Split transaction button always accessible (outside scroll area), opens modal
- [x] Split transaction "add remaining to category" button
- [x] In-place split conversion (2026-08-02): `POST /transactions/{id}/split` converts a row into a split parent, preserving attachments/AI links/sync ids — replaces the create+delete flow in the editor (which orphaned attachments); editor split-on-edit now routes through it

### AI (Ollama) — receipt scanning, NL/voice entry, activity log (2026-08-02)
- [x] Receipt photo → AI-extracted transaction: mobile quick-add "Scan receipt" queues a persistent job (`ai_jobs` table, migration b3f1c8a7d2e9); in-process asyncio worker (startup recovery, exponential backoff, SKIP LOCKED claims) extracts payee/total/date/category via Ollama vision (`format=json`, temp 0, category names not UUIDs) and creates an `approved=false` transaction with the image attached + `created_via='ai_receipt'`; terminal parse failure still creates a $0 stub with the image so the receipt is never stranded; retry refills an untouched stub
- [x] Review modal: TransactionEditor review mode — zoomable receipt pane (Lightbox/pinch) beside the form, confidence banner, "Apply suggested split" from line items (never auto-applied), Approve button
- [x] Suggested multi-category split from receipt line items: stored on the job result, offerable only when every line resolves and sums match within 1¢
- [x] NL + voice entry, one DRY path: `POST /{budget}/ai/parse-transaction` (audited as `nl_parse` jobs) → draft prefills the existing TransactionEditor (`ai_job_id` links back, server stamps `created_via='ai_nl'`); Sparkles button in register toolbar + "Describe it" in quick-add; Web Speech API dictation (feature-detected, transcript confirmed before parse, mic hidden where unsupported)
- [x] AI Activity page (`/ai-activity`, hidden when AI unconfigured): permanent audit log with status chips, error details, retry/delete, receipt thumbnails, view-transaction links; header badge with active-job count (fast poll only while active); Sidebar/MoreSheet entries
- [x] Model-agnostic capabilities: `/api/show` probe — thinking auto-enables when advertised (`ai_thinking` auto/on/off), vision pre-checked at submit with a clear error; pass-through `ollama_options` + `ollama_vision_options` JSON and `ai_vision_timeout_s` in Settings → AI → Advanced; optional `ollama_vision_model` override toggle
- [x] Editable AI prompts: all 4 task prompts viewable/editable in Settings (only overrides stored; revert-to-default via `DELETE /settings/{key}`); broken placeholders fall back to defaults; brace-safe literal substitution
- [x] Register: per-row image button (muted = add, accent = view w/ lightbox) replacing the passive paperclip; `has: attachment` / `NOT has: attachment` search syntax → `has_attachment` param on both list endpoints
- [x] Attachment path integrity fix: `storage_path` recorded at upload (migration backfills) — date edits after attach no longer orphan files
- [x] AI payee polish: "Normalize" button in the merge modal (uses normalize-payee endpoint); `BudgetAccess` ownership guard added to the pre-existing AI routes
- [x] PDF attachments (2026-08-02): `application/pdf` accepted everywhere images are (attachment panel, quick-add, row button, AI scan); stored verbatim with a rendered-first-page WebP thumbnail; PDFs open in the browser's native viewer (new tab / iframe in the review pane); AI extraction rasterizes the first page via PyMuPDF (AGPL-3.0 — deliberate copyleft choice)
- [x] Receipt gate (2026-08-02): cheap "is this a receipt?" vision check (tiny output budget, thinking never enabled, editable `ai_prompt_receipt_gate`) before full extraction; not-a-receipt is terminal → same $0 stub-with-image path as failures; inconclusive answers proceed so the gate can never block a real receipt
- [x] Desktop scan entry point (2026-08-02): "Scan a receipt instead" in the add-transaction editor (create mode, AI-gated) queues the same receipt job with the editor's selected account

### Data
- [x] Generate sample budget (2026-07-25: one-click card on the budget selector + `just sample-budget <email>` CLI; 12 months of curated data — 5 account types, splits, transfers, targets, tags, scheduled, reconciliation; generator derives assignments from the data and sweeps surplus into Emergency Fund so TBA lands exactly at $150 with only Dining Out overspent, for any anchor date; integrity green, 7 integration tests)
- [x] Auto backups configurable in UI (2026-08-10: Settings → Backups panel — interval/retention/keep-min/age-recipient stored in `app_settings` (env vars remain seeds + fallbacks), polled by the db-backup agent every 10s via psql so changes apply without restart; agent online/offline indicator, backup-now button, list of existing backups (kind/size/date/encrypted), and in-app restore: confirm dialog + optional pre-restore safety dump, file-based command protocol (`/backups/.agent/`), maintenance-mode 503s with DB-free status endpoint, API self-restarts onto the restored DB (kills its parent chain — needed under `UVICORN_RELOAD`); encrypted + attachments restores deliberately CLI-only since the server holds no age private key; live-tested full round-trip incl. restart)
- [x] Backup hardening with sensible defaults (2026-08-10: inline compose loop → `scripts/db-backup.sh` — atomic temp-file+rename writes, keep-at-least-N floor so a silent month of failures can't prune the last good backups (KEEP_MIN=7), failed dump skips pruning, attachments now archived too (`igab-attachments-*.tar.gz`, only when contents changed via md5 manifest), all vars documented in .env.example, README updated; live-tested incl. restore of both artifact kinds)
- [x] Encrypted backups: optional `age` public-key encryption in the db-backup container (2026-08-10: `BACKUP_AGE_RECIPIENT` env var encrypts dumps + attachment archives as `.age`; age installed in-container on demand; `just restore <file>.age` decrypts via `BACKUP_AGE_KEY_FILE`; restore docs in README; verified decrypt round-trip). Decision 2026-08-10: no DB/field-level encryption at rest — server-side queries need plaintext and host disk encryption (Unraid LUKS) is the right layer for stolen-disk risk; documented in README. Secrets stay app-encrypted (SimpleFIN Fernet)
- [ ] YNAB-compatible export (exit strategy — a system of record needs a way out too)
- [ ] Attachment file GC (files of long-deleted transactions are never removed from disk)

### Accounts & Finance Tools
- [ ] Savings tools section (personal finance flowchart, savings guidance)
- [ ] Education section (personal finance flowchart, other resources)
- [ ] Migrating to a new budget plan (preserve transaction history)
- [x] Monthly category balance snapshots (O(1) budget summary, invalidate on change) — done 2026-08-12: `category_month_snapshots` + `budget_snapshot_meta` tables (meta-row presence = validity), write-through invalidation hooks in `db/invalidation.py` on every mutation that can shift balances; `get_budget_summary` reads snapshots when valid, rebuilds+persists when not; 22 integration tests (recompute-parity oracle + invalidation matrix)
- [x] Budget lookback / month comparison (side-by-side via snapshots) — done 2026-08-12 as the Phase B3 multi-month view below

### Testing & CI
- [ ] CI on push (GitHub Actions: `just quality` + backend suite with a Postgres service container + `npm run typecheck`) — deferred while development is active; run the suite manually before commits meanwhile
- [x] Frontend tests for money-critical components (transaction editor, split editor cents math, bulk flows) — done 2026-08-10: vitest + jsdom + testing-library harness (`frontend/src/test-utils/setup.ts`, `vite.config.ts` test block); added TransactionEditor (signing, overspend gate, split validation), SplitTransactionEditor (integer-cents math), and SelectionActionBar (bulk wiring) suites — 13 files / 217 tests, ~1s via `npx vitest run`

### Localization
- [x] Settings for currency, decimal vs comma separator, date format (CSV import now handles EU separators exactly; UI display settings remain)
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
- [ ] inflation-adjusted trends, "if invested instead" — need external_series infra (sketched in roadmap)
- [ ] R3 auto-detection — cadence detection algorithm, confidence scoring, "suggest tags" UI

### Other
- [x] Locale/format settings — per-budget number format (1,234.56 vs 1.234,56 vs 1 234,56), date format (M/D/Y vs D/M/Y vs Y-M-D), time format (12h vs 24h) — Settings page UI + app-wide FormatContext
- [ ] 2FA (TOTP) support — deferred 2026-08-10: self-hosters can front IGAB with Authelia/Authentik/etc.; revisit only if demand appears
- [x] Budget notes / annotations
- [ ] Transaction flags / colors
- [x] Multi-currency support (transactions in foreign currencies)
- [ ] Plugin framework + plugin management page
- [ ] Mock SimpleFIN API for dev (a FakeClient exists in the integration tests; a dev-mode mock server with generated timestamps does not)
- [x] Budgeted-mode sankey ignores account filters (pre-existing backend inconsistency; spent mode honors them — compare mode inherits it) — fixed 2026-08-10: budgeted mode now applies the account filter to its transaction-derived income total; assignment flows stay budget-level (assignments have no account dimension — info popover explains this) + integration test

### Competitive review — budgero (2026-08-10, github.com/tombadilo-bombadilo/budgero)
_Reviewed their feature set + Unraid packaging. Their model diverges from ours deliberately: RTA is a single global time-static number, and overspending stays in-category instead of being deducted from RTA — simpler, but our YNAB-style month-aware TBA is more correct; keep ours. Their "semantic search" is marketing: it's a structured token parser (date phrases, amount filters, category/label tokens) over substring matching, no embeddings. Items below are what's worth adopting._

_Phased build plan (2026-08-10): ordered by value-per-effort — correctness first, then cheap high-value wins, then the big builds, then packaging; the last phase is deferred-until-demand. Effort tags S/M/L. Every item states its mobile handling explicitly._

_Agreed execution order (2026-08-10): 1) data backups working with sensible defaults (incl. encrypted-backups item under Data) → 2) B1 + frontend test harness (Testing & CI) → 3) budgeted-mode sankey account-filter fix → 4) B2 → 5) B3 → 6) B4 → 7) host on Unraid and run the cutover parallel-test there (no local spin-up). 2FA/TOTP deferred: self-hosters can front the app with Authelia/Authentik or similar._

#### Phase B1 — Correctness (do first: small diffs, highest value; core trust surface → exhaustive tests per CLAUDE.md)
- [x] (S) Reconciliation as-of cutoff: `ReconciliationService.get_status` sums all cleared transactions regardless of date, so a future-dated cleared transaction skews the cleared balance and produces a wrong adjustment vs the bank statement. Exclude transactions dated after today in `get_status`/`finish` (budgero shipped this exact fix in their changelog). Tests: future-dated cleared txn present → status and adjustment unchanged. Mobile: none — reconciliation UI already responsive — done 2026-08-10: `as_of=today_utc()` cutoff in get_status/finish; future-dated cleared txns excluded from cleared balance and left unlocked on finish + tests
- [x] (M) Future-month assignments vs TBA: `get_budget_summary` simulates category balances only through the viewed month, so assigning $500 in September doesn't reduce August's TBA — the same dollars can be assigned twice. Decide handling (YNAB deducts future assignments from current RTA, or show an explicit "Assigned in Future" line on the hero) + tests for assign-ahead → navigate back. Mobile: whatever surfaces on the desktop hero pill must also appear in the mobile TBA hero drawer (BottomSheet), not just desktop — done 2026-08-10: YNAB behavior (TBA deducts assignments after the viewed month via `assignment_repo.sum_after_month`); `assigned_in_future` exposed on BudgetMonthResponse and surfaced on the hero pill + shared TbaDrawer (renders in both desktop drawer and mobile BottomSheet) + tests
- [x] (S, rides on the previous item's machinery) Future overspending warning: when an edit made today pushes a *future* month's category available negative (e.g. spending against a category that has future assignments), warn with option to proceed. Mobile: warning must render in the full-screen mobile editor and quick-add sheet, not only the desktop inline editor — done 2026-08-10: `POST /{budget_id}/months/preview-overspend` (BudgetService.preview_future_overspend, signed deltas aggregated by category+month, handles splits and edit reversals) + `confirmFutureOverspend` gate in TransactionEditor (desktop + mobile full-screen) and QuickAddSheet via native confirm(); warn-only — API failure never blocks a save + 7 integration tests

#### Phase B2 — Quick wins (each roughly a day; immediately felt daily)
- [x] (M) Calculator amount inputs — ONE shared expression-evaluating amount component/hook, used everywhere: desktop inline assignment cells (`+50`, `-25`, `*2` against current value), TransactionEditor amount, split-editor line amounts, and the mobile QuickAddSheet amount-first entry (summing receipt items on the phone — `12.50+3.99` — is the killer use). Evaluate on blur/Enter/`=`; cents-integer math, no float eval; invalid expression keeps prior value with a shake/hint — done 2026-08-11: `utils/amountExpression.ts` (cents-integer evaluator, relative `+50`/`*2` mode) + shared `AmountInput` component (blur/Enter/`=` eval, shake on invalid); wired into CategoryRow assignment cells, TransactionEditor, SplitTransactionEditor, QuickAddSheet (with operator chips), and TransactionRow inline edit; unit + component tests
- [x] (S) Privacy mode: app-wide amount-masking toggle for screen-sharing / over-the-shoulder use. Route all money rendering through the existing FormatContext so it's one switch; per-device persistence (localStorage). Desktop: command palette entry + keyboard shortcut. Mobile: toggle in MoreSheet (palette is desktop-only) + optional header eye icon — done 2026-08-11: `privacyMode` in persisted appStore, masking in useFormatters (`$••••`, sign hidden so overspending can't be inferred); Shift+P shortcut, palette "Toggle privacy mode" entry, header eye button, MoreSheet toggle
- [x] (S–M) "Reduce overfunding" auto-assign strategy: pull categories over their target back down to target, returning the excess to TBA (complements existing underfunded/cover-overspent strategies); signed-delta preview modal like the other strategies, apply recomputes server-side through move_money. Mobile: inherits automatically via the existing Assign BottomSheet drawer — done 2026-08-11: `reduce_overfunded` strategy in AssignService (same overfunded definition as the quick filter: assigned > target amount, works while overspent); dropdown row + preview modal + mobile via existing machinery; integration tests incl. idempotency and overfunded-while-overspent
- [x] (M) Search upgrades in searchParser.ts: natural-language date tokens ("today", "yesterday", "last week/month/year", month names, explicit ranges → existing start_date/end_date params) + type tokens (`is:inflow`, `is:outflow`, `is:transfer`); render matched tokens as removable filter chips above the register. Mobile: chips become a horizontally scrollable row under the search input on the cards view; tokens stay typeable since the palette is desktop-only — done 2026-08-11: date tokens (today/yesterday/this|last week|month|year/month names with optional year and jan-mar ranges, Mon–Sun weeks, past-year inference) + `is:inflow/outflow/transfer` and `NOT is:transfer`; backend `direction`+`is_transfer` filters on both listings; `SearchFilterChips` removable chip row (horizontally scrollable on mobile); parser/chip unit tests + backend integration tests

#### Phase B3 — Bigger builds (high value, real effort)
- [x] (M) Plan vs Reality report: assigned vs actually spent per category per month, surfacing chronically over-budget categories (Insights group). Mostly assembly — existing report infra, drill-down panels, and export patterns apply. Mobile: nothing special, reports are already responsive — done 2026-08-12: `GET /reports/plan-vs-reality` (carryover-ignoring monthly variance; "over" = spent > assigned in active months; chronic = over in ≥3 of last 6 window months, sorted chronic-first) + Insights tab: variance matrix with severity-scaled overspend tint, 6/12/24-month selector, chronic-only toggle, per-cell and full-window drill-down, wide-format CSV export; 6 backend integration tests + matrix component tests
- _(prerequisite)_ Monthly category balance snapshots — done 2026-08-12, tracked under Accounts & Finance Tools above
- [x] (L) Side-by-side multi-month view: desktop-only sheet/overlay from the budget page showing 3–6 month cards (user-selectable count), editable assignments with changes rippling into later months, month anchor navigable independently of the main view, category search filter within the sheet. Budgero gates it at ≥1600px viewports and just runs N parallel month queries — snapshots make it cheap instead. Mobile: deliberately not ported — month-swipe (useSwipeNavigation) already covers sequential comparison; instead add a cheap "vs last month" delta line (assigned/activity/available) to the category inspector sheet — done 2026-08-12: full-screen `MultiMonthSheet` ("Months" button on the TBA hero, desktop only) — no new endpoint; `useQueries` fan-out over the existing month endpoint (snapshot-fast, shared React Query cache), sticky category column + two-row month headers with per-month TBA, group subtotal rows, expression-aware editable assignment cells, independent anchor nav, 3–6 count picker, category filter, Escape layering; assignment mutations now invalidate all cached months (ripple correctness — set/move/auto-assign/assign-apply/cover-overspent); mobile "vs last month" delta line added to the inspector's Available Balance breakdown

#### Phase B4 — Self-host & Unraid packaging (independent of B1–B3; schedule around the cutover)
_Budgero ships a single Go binary + embedded SQLite: one container, one port, one /data volume, one required env var, ~200MB RAM, CA template in their own template repo. We're a 3-container stack (Postgres + API + nginx) — can't match single-container without an architecture change, but can make Unraid first-class:_
- [ ] (M) Publish multi-arch (amd64/arm64) images to GHCR on tag/release (api + nginx-frontend) — prerequisite for any Unraid story; currently images only build locally via compose
- [ ] (S) Docs for Unraid's "Docker Compose Manager" plugin driving our existing compose file as-is — cheapest viable Unraid path, do before templates
- [ ] (M) Unraid CA template repo (like their unraid-templates repo): templates for the API + frontend containers with a documented official-Postgres pairing, appdata volume layout (`/mnt/user/appdata/igab/` for pg data, attachments, backups), required env vars surfaced with descriptions (SECRET_KEY, ADMIN_EMAIL/ADMIN_PASSWORD, DATABASE_URL preset to the paired Postgres, VITE_API_URL/origin config); migrations already run on API container start so no manual step
- _(pairs with)_ Encrypted backups — tracked under Data above; do alongside the template/docs work so self-hosting docs land once
- [ ] (S–M) In-app update notification for self-hosted installs (opt-in, off by default): compare running version against GitHub releases, surface a toast/badge. Mobile: badge on MoreSheet entry mirrors the desktop sidebar badge

#### Phase B5 — Deferred until demand (nice-to-haves that may not be worth the effort)
- [ ] (L) Rules engine (their "auto rules"): conditions on payee/memo/amount/account (equals/contains/regex, AND-combined); ordered actions (set category/payee/memo, strip-from-memo via regex, set/adjust amount, reroute account); three modes — continuous (fires on import/sync/manual create), one-time retroactive run, autofill (suggestion-only in the editor); per-rule run history + one-click undo of the last run (the undo safety net is the trust feature that makes automation acceptable). Deferred because payee regex match patterns, most-recent-category auto-categorization, and scheduled transactions already cover the payee-normalization core — revisit after a few statement cycles on live data; if memo-cleanup/amount-tweak/retroactive-fix pain shows up, build as a v2 of the payee-matching system rather than a parallel engine
- [ ] (M–L) True semantic search (AI-gated): embed payee+memo via an Ollama embedding model into pgvector, hybrid-rank with existing ILIKE + structured filters — only if the B2 token parser proves insufficient in practice
- [ ] (L) All-in-one image (s6/supervisord running postgres+api+nginx in one container, single appdata volume) — the Unraid-native UX; only if templates + compose docs prove painful for real Unraid users

#### Noted but not adopting
- Global time-static RTA and overspending-stays-in-category (keep YNAB semantics); labels (our tags are a superset — multiple per transaction); local-first browser-SQLite + E2E-encrypted sync (whole different architecture); DuckDB SQL explorer + custom dashboards (our reports cover it; revisit if power-user querying demand appears); warranties tracker; crypto accounts with daily revaluation; Push API + email bridge (SimpleFIN + AI receipt scan cover ingestion)

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


- backend and frontend test coverage reports


ideas:
- create a mock api for dev instead of calling the simplefin api, it calls this and returns a static set of data. though it would have to be generated for a relevant time stamp or something?


<!-- receipt extraction into split transactions: DONE 2026-08-02 (suggested_split from line items in the review modal). A UPC database lookup for decoding cryptic item strings remains a possible future enhancement — line_items keep the original strings in the job result. -->

<!-- - receipts should be stored as a scan? or allow the phone to use the scan feature. this is to help with image sizes as well as potentially with ocr (partially addressed: images sent to the model are downscaled to 1536px JPEG; stored attachments remain WebP) -->
- more account types like investment accounts, etc?

- need to have a means to have/handle credit cards / other budget accounts in the budget view. like a section for credit cards, savings, etc. kinda like how ynab handles them a bit. need to find an explanation of how it works and try to remember/articulate why it was confusing for me.

fixes:
- 

todo:
- fable audit/ review for common component usage and remove arbitrarily unique components



<!-- receipt parsing with gemma4 + ollama: DONE 2026-08-02 — see "AI (Ollama)" section in the Backlog. Queue, needs-review transaction, payee/category memory reuse, and the error-stub-with-image behavior all implemented as described here. -->





- a report idea for showing progress in reducing spending habits. not sure what that might look like but maybe as part of the savings plan/assistance stuff there could be a spending behavior/relationship improvement thing. the user sets a goal of how much to reduce their 'unnecessary' spending and they can see how that's going over time. would need a way to identify/categorize necessary spending.


- paperless-ngx integration for a locally running instance of that. if configured, documents should be sent to that with a thumbnail stored locally. images should be tagged for the budget, with a uuid, and other information to tie it back to the transaction. this allows for the documents to be stored in one place for the user to search, etc.
  - api docs: https://docs.paperless-ngx.com/api/#document-versions
  - requires auth stuff to be saved for the requests
  - if this isn't added, docs get stored in full resolution on volume specified during setup, if it is, then only thumbnail-ish (or the size used to send to the ai) gets stored in the volume while full image gets sent to paperless-ngx. Not sure if that's the best route or if it should be more involved interaction between the two for things like search and all that. I feel like that would make the UI really unresponsive trying to query for that. unless it's done only when looking at the transaction or something.
  - 
