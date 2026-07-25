# Future Reports Roadmap

Full designs — backend, UX, implementation guides, and test plans — for the deferred
reports in CHECKLIST.md. Each phase (R1–R7) is written to be implementable standalone
by an engineer or model with no prior context: schemas, endpoint contracts, algorithm
pseudocode, file-level touch lists, and acceptance criteria are all here. Do not
re-derive decisions at implementation time; if a decision must change, update this doc.

_Status: designed 2026-07-22. Nothing implemented yet._

## Decisions (2026-07-22)

- Tags apply to **categories and payees** (transaction-level tags deferred until a
  concrete need appears).
- Subscriptions use **auto-detect + user curation**: detection proposes with cadence
  and confidence; the user confirms or dismisses; confirmation is what makes a
  subscription "real" for reports. No auto-confirm, ever.
- Priority after subscriptions: anomaly detection + payday effect → cash projection →
  debt payoff. Inflation-adjusted trends and "if invested instead" stay deferred
  (external-data infra is sketched at the end, nothing more).
- Tag colors are **named theme slots, not stored hex** — a stored hex would clash with
  at least some of the 9 themes.
- Debt amortization lives in a **standalone `Debt` entity** (added 2026-07-24), not
  CategoryTarget and not exclusively an Account. A debt can optionally point at an
  existing loan Account ("managed" — balance/history come from the real ledger) or
  stand alone ("unmanaged"/passive — manual balance, optionally fed by a linked budget
  category's spending). This supersedes the old checklist note "needs loan
  amortization in CategoryTarget" and the earlier `loan_details`-on-Account sketch.
- The category↔debt link (added 2026-07-24) is a **dedicated `linked_debt_id` FK on
  Category**, mirroring the existing `linked_account_id` pattern for credit-card
  payment categories — not the tags system. Tags stay freeform labels; a debt link is
  a one-to-one relational fact, so it gets its own FK, mutually exclusive with
  `linked_account_id`.

## Handoff conventions

Rules the implementing model must follow (they restate CLAUDE.md + observed codebase
conventions; the codebase wins on any conflict):

- **Backend**: async throughout; repos inherit `BaseRepository[ModelT]`
  (`backend/src/igab/repositories/base.py`); services take injected repos; Pydantic
  schemas in `backend/src/igab/api/v1/schemas/`; routers registered in
  `backend/src/igab/api/v1/router.py`. **Every endpoint is ownership-scoped to the
  authed user's budget** — follow the two-user 404 pattern in
  `backend/tests/integration/test_authorization.py` and add cases there for every new
  endpoint. Amounts are `Numeric(19, 4)` in the DB and Python `Decimal` end-to-end.
  Soft delete via `is_deleted`; association rows hard-delete.
- **Migrations**: `backend/alembic/versions/`, sequentially numbered
  (`0001_initial`, `0002_transaction_location` exist). Numbers used below
  (0003/0004/0005) assume landing order — renumber to the next free slot when landing.
- **Quality gates**: `just quality` (ruff fix + format + ty) before finishing any
  backend change; `just typecheck` (tsc) for frontend; `just test-backend` runs the
  suite (real-Postgres integration tests included).
- **Testing**: per CLAUDE.md, anything touching amount calculations needs exhaustive
  coverage — zero balances, negative amounts, rounding, partial data. Add factories to
  `backend/tests/integration/factories.py` for every new model.
- **Frontend**: per-component CSS files; CSS custom properties only — never hard-code
  colors, all 9 themes must work; React Query hooks in `src/api/`; Zustand stores in
  `src/stores/`; recharts for charts; lucide-react for icons; mobile breakpoint
  `@media (max-width: 768px)`; 44px touch targets; 16px font on mobile inputs
  (prevents iOS zoom).
- **Design language** (`.impeccable.md`): Steady, Clear, Trustworthy. Calm by default —
  color only for meaningful state. Information density is a feature. No flashy fintech,
  no red-badge nagging.

### Cross-cutting quality bar

Every new report tab ships with all of:

1. An info (i) modal (`ReportInfoButton` pattern) that explains the method **honestly**,
   including its limits — what's computed, what's excluded, why something might be
   missed or wrong.
2. `ReportExportButton` (CSV / JSON / PNG) wired up.
3. Drill-down support wherever a row or chart element maps to transactions (existing
   `DrillDownPanel` — construct a `DrillDownContext` at click time, zero panel changes).
4. A **designed** empty state. An empty anomaly report is good news and should feel like
   it. Never a bare "No data."
5. A ≤768px layout: tables become cards, actions become full-width, charts shrink to
   ~240px height.
6. A visual pass across all 9 themes before calling it done.

## Shared UX primitives (built in R1, used by everything after)

### Existing inventory to build on (verified)

- **Tokens** (`frontend/src/themes/base.css` + 9 theme files):
  `--bg-primary/secondary/tertiary/elevated/hover`,
  `--text-primary/secondary/muted/inverse`,
  `--color-accent/accent-hover/positive/negative/warning/info`,
  `--border-color/subtle`, `--spacing-xs/sm/md/lg/xl` (4/8/16/24/32),
  `--border-radius-sm/md/lg` (4/8/12), `--font-size-xs/sm/base/md/lg/xl`
  (11/13/14/15/18/22), `--shadow-sm/md/lg`, `--transition-fast/base`,
  `--input-focus-shadow`.
- **Pill precedent**: `components/budget/TargetBadge.css` — `2px 6px` padding, 10px
  radius, 10px font, weight 600, `color-mix(in srgb, var(--color-*) 20%, transparent)`
  background with full-strength color text.
- **Curation precedent**: `components/simplefin/MatchReviewModal.tsx/.css` —
  `.match-modal__actions` (accent accept / `--color-surface` reject buttons),
  `.match-modal__confidence` bar.
- **Pickers**: `components/common/Combobox` (desktop) and
  `components/common/SelectionSheet` (mobile: 44px rows, create-option, check icons).
- **Bulk actions**: `components/common/FloatingSelectionBar` (compound component with
  `FloatingSelectionBar.Button`).
- **Settings**: `.settings-section` card → `__header` (uppercase xs title) → `__body` →
  `.settings-row`.
- **Reports**: `.report-section` cards, `MetricCard`, `ReportInfoButton`,
  `ReportExportButton`, `DrillDownPanel`, `.reports-empty`, `chartColors.ts` palette.
- **Toasts**: react-hot-toast.

### New primitive: `TagChip`

`frontend/src/components/common/TagChip/TagChip.tsx` + `.css`.

- Props: `{ name: string; colorSlot?: TagColorSlot; onRemove?: () => void }`.
- Inline-flex pill: `padding: 2px 8px; border-radius: 10px; font-size: 10px;
  font-weight: 600; letter-spacing: 0.3px; white-space: nowrap`.
- Fill: `background: color-mix(in srgb, var(--tag-<slot>) 18%, transparent);
  color: var(--tag-<slot>)`. No slot → `color: var(--text-secondary);
  background: var(--bg-tertiary)`.
- `onRemove` renders a 12px lucide `X` — used only inside pickers/forms, never in
  read-only displays.

### New tokens: tag color slots

`TagColorSlot = 'red' | 'orange' | 'yellow' | 'green' | 'teal' | 'blue' | 'purple' | 'pink'`

Add `--tag-red … --tag-pink` to `themes/base.css` (fallback values) and to **each of
the 9 theme files**, with values drawn from each theme's own source palette — Gruvbox
red is Gruvbox's red, Nord red is Nord's `nord11`, Catppuccin uses its named accents.
Honor the source material; do not reuse one hex across themes.

### New composition: `TagPicker`

`frontend/src/components/common/TagPicker/` — composition of existing pieces, not new
machinery.

- Desktop: popover multi-select built like the reports `MultiSelectCombobox` — search
  input, option rows with checkmarks, selected tags as removable `TagChip`s, and a
  "Create '<text>'" bottom row when `allowCreate` and no exact match.
- Mobile (≤768px): `SelectionSheet` (already supports create-option and check states).
- Props: `{ selectedTagIds: string[]; onChange: (ids: string[]) => void;
  allowCreate?: boolean }`. Create posts `POST /tags` with no color slot, then selects
  the new tag.

### Curation row pattern (documented arrangement, not a component)

Content left → confidence indicator → `Confirm` (accent background, `--text-inverse`
text) + `Dismiss` (`--color-surface` background, `--text-primary` text), styled per
`.match-modal__btn`. Used by the subscription review strip (R3) and any future review
flow.

---

## R1 — Tags foundation (M)

**Goal**: first-class tags on categories and payees — schema, CRUD, management UI, and
pickers — so later phases can attach semantics (`savings` routing, `subscription`
marking) to a stable foundation.

### Backend design

**Migration `0003_tags` + `backend/src/igab/db/models.py`:**

```python
class Tag(Base):
    __tablename__ = "tags"
    id:          UUID  pk
    budget_id:   UUID  FK budgets.id ondelete=CASCADE, nullable=False, index=True
    name:        String(50), nullable=False
    system_key:  String(30), nullable=True   # 'subscription' | 'savings' | 'long_term_expense'
    color_slot:  String(20), nullable=True   # TagColorSlot names; NULL = neutral chip
    is_deleted:  Boolean, default=False
    created_at / updated_at: DateTime(timezone=True)
    __table_args__: UniqueConstraint(budget_id, name), UniqueConstraint(budget_id, system_key)

category_tags = Table(   # association — hard-delete rows, no surrogate id
    Column("category_id", FK("categories.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id",      FK("tags.id",       ondelete="CASCADE"), primary_key=True))

payee_tags = Table(      # same shape
    Column("payee_id", FK("payees.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id",   FK("tags.id",   ondelete="CASCADE"), primary_key=True))

# Category.tags / Payee.tags: relationship(secondary=..., lazy="noload")
# — endpoints opt in with selectinload.
```

The migration seeds the 3 system tags for every existing budget with default slots:
`subscription`→`purple`, `savings`→`green`, `long_term_expense`→`teal` (display names
"Subscription", "Savings", "Long-term expense"). `budget_service` seeds the same on
budget creation. System tags may be renamed and recolored; DELETE returns 409.

**New `backend/src/igab/repositories/tag_repo.py`** (`BaseRepository[Tag]` plus):

- `list_for_budget(budget_id) -> list[Tag]` — not deleted, ordered by name, with
  category/payee usage counts (two grouped-count subqueries, attached to the result).
- `set_category_tags(category_id, tag_ids)` / `set_payee_tags(payee_id, tag_ids)` —
  replace-set: delete association rows not in the list, insert missing ones.
- `add_payee_tag(payee_id, tag_id)` / `remove_payee_tag(payee_id, tag_id)` — additive
  single-tag helpers (used by bulk tagging and R3 confirm/dismiss).
- `get_system_tag(budget_id, system_key) -> Tag`.
- `get_category_system_keys(budget_id) -> dict[UUID, set[str]]` — one query joining
  `category_tags → tags` where `system_key IS NOT NULL` (consumed by report_service
  in R2).

**New `backend/src/igab/api/v1/tags.py`** + `schemas/tag.py`, registered in
`router.py`. All ownership-scoped.

| Endpoint | Body | Returns | Errors |
|---|---|---|---|
| `GET /{budget_id}/tags` | — | `list[TagOut]` = `{id, name, system_key, color_slot, category_count, payee_count}` | |
| `POST /{budget_id}/tags` | `{name, color_slot?}` | `TagOut` 201 | 409 duplicate name |
| `PATCH /{budget_id}/tags/{tag_id}` | `{name?, color_slot?}` | `TagOut` | 409 duplicate name |
| `DELETE /{budget_id}/tags/{tag_id}` | — | 204 — soft-deletes tag, hard-deletes join rows | 409 if `system_key` set |
| `PUT /{budget_id}/categories/{id}/tags` | `{tag_ids: [UUID]}` | `list[TagOut]` | 404 tag from another budget |
| `PUT /{budget_id}/payees/{id}/tags` | `{tag_ids: [UUID]}` | `list[TagOut]` | 404 tag from another budget |

`CategoryOut` and `PayeeOut` gain `tags: list[TagOut]` (touch `api/v1/categories.py`,
`api/v1/payees.py` + schemas; use `selectinload` — watch N+1 on list endpoints).
`color_slot` is validated against the 8 slot names (422 otherwise).

### UX design

- **Settings → Tags**: new `components/settings/TagsPanel/TagsPanel.tsx + .css`,
  mounted in `SettingsPage.tsx` between the Budget and Accounts sections. A
  `.settings-section` card listing rows
  `[TagChip preview · name · "3 categories · 2 payees" (xs muted) · Edit · Delete]`
  per the `.settings-account-item` pattern. Edit swaps the row inline: name input +
  swatch row (8 filled 16px circles colored by `--tag-*`; selected swatch ring
  `box-shadow: 0 0 0 2px var(--color-accent)`) + Save/Cancel. System tags show a lucide
  `Lock` (14px, `--text-muted`) in place of Delete, tooltip: "Used by reports — rename
  or recolor only." Bottom add form: input + swatch row + accent Add button.
- **CategoryInspector**: new
  `components/budget/CategoryInspector/TagsSection.tsx`, placed after the Notes
  section, following the section pattern (`.inspector-section`, xs uppercase title
  "TAGS"). Read state: wrapped chip row
  (`display: flex; flex-wrap: wrap; gap: var(--spacing-xs)`). A "+ Tag" ghost button in
  `.inspector-section__actions` opens `TagPicker`. Budget grid rows are deliberately
  untouched — tags live in the inspector; the grid stays calm.
- **PayeesPage**: new Tags column between Transactions and Actions — chips, max 2
  visible + a "+N" overflow chip whose tooltip lists the rest. The existing inline edit
  mode gains a `TagPicker`. `FloatingSelectionBar` gains a "Tag" button (lucide `Tag`)
  → `TagPicker` in **additive** mode: adds the chosen tags to all selected payees, no
  bulk removal (keeps bulk semantics unambiguous). This is the fast path for
  hand-marking a batch of subscription payees.
- **New `frontend/src/api/tags.ts`**: `useTags`, `useCreateTag`, `useUpdateTag`,
  `useDeleteTag`, `useSetCategoryTags`, `useSetPayeeTags` — mutations invalidate
  `['tags']`, `['categories']`, `['payees']`.

### Implementation guide

1. Migration `0003_tags` + models + relationships; run `just dev-migrate`.
2. `tag_repo.py`; seed logic in migration + `budget_service`.
3. `api/v1/tags.py` + `schemas/tag.py`; register router; extend category/payee
   responses.
4. Factories (`TagFactory`) + backend tests (see test plan); `just quality`,
   `just test-backend`.
5. `--tag-*` variables in `themes/base.css` + all 9 theme files.
6. `TagChip` → `TagPicker` → `api/tags.ts`.
7. `TagsPanel` in Settings → inspector `TagsSection` → PayeesPage column + bulk button.
8. `just typecheck`; 9-theme visual pass.

### Test plan

- Replace-set semantics: add, remove, no-op, empty list clears all.
- System-tag DELETE → 409; user-tag delete removes join rows.
- Duplicate name → 409 (case handling consistent with payee-name uniqueness).
- Cross-budget `tag_ids` in PUT → 404, nothing written.
- Two-user ownership 404s on all 6 endpoints (`test_authorization.py`).
- Seed idempotence: migration on existing budgets + creation of a new budget both
  yield exactly 3 system tags.
- Category/Payee list endpoints include tags without N+1 (query-count assertion if the
  harness supports it).

### Acceptance

Create/rename/recolor/delete tags in Settings across themes; tag a category from the
inspector and a payee from the list and via bulk bar; chips render correctly in all 9
themes; suite green.

---

## R2 — Tag-aware report semantics (S, depends on R1)

**Goal**: make tags mean something in reports — savings-tagged categories read as
saving (not spending) in the Sankey, can be excluded from Pareto/Treemap, and tags
join the shared report filter bar. Delivers the long-standing checklist idea: a
savings category funded from a single monitored account should not look like spending.

### Backend design

`backend/src/igab/repositories/txn_filters.py` gains three functions (keep the
module's docstring style — document the aggregation rule each encodes):

```python
def category_tag_filter(tag_ids: Sequence[UUID]) -> ColumnElement:
    # Transaction.category_id.in_(
    #     select(category_tags.c.category_id).where(category_tags.c.tag_id.in_(tag_ids)))

def payee_tag_filter(tag_ids: Sequence[UUID]) -> ColumnElement:
    # same shape over payee_tags / Transaction.payee_id

def exclude_category_system_keys(budget_id, keys: Sequence[str]) -> ColumnElement:
    # Transaction.category_id NOT IN (category ids whose tags have system_key in keys)
```

- Report endpoints `spending`, `spending-grouped`, `payee-analysis`, `day-patterns`,
  `large-transactions` accept `tag_ids: list[UUID] | None`, threaded exactly like the
  existing `category_ids` params. `spending-grouped` also accepts
  `exclude_tag_keys: str | None` (comma-separated system keys).
- **Sankey savings routing** (`report_service.py`, `_cash_flow_spent`): fetch
  `tag_repo.get_category_system_keys()` once per request; categories tagged `savings`
  or `long_term_expense` route to a new terminal node `{id: 'savings',
  type: 'savings'}` instead of the spending branch, keeping per-category child nodes
  under it. Totals must still reconcile.
- Pattern for any future tag-aware report: join the system-key map as boolean columns
  on the Polars DataFrame — one map fetch instead of retrofitting LEFT JOINs into 15
  hand-built queries.

### UX design

- `reportStore.ts`: `ReportFilters` gains `tagIds: string[]` (default `[]`, cleared by
  `resetFilters`); `TabFilterSupport` gains `tags: boolean` — add to all 15 existing
  entries: `true` for `pareto`, `treemap`, `payees`; `false` elsewhere.
- `ReportFiltersBar`: a Tags `MultiSelectCombobox` appended to `.rfb__selects`, options
  rendered with their chips; dims on unsupported tabs per the existing convention
  (dimmed, never silently ignored).
- **Sankey**: savings node fill
  `color-mix(in srgb, var(--color-positive) 30%, var(--bg-tertiary))`; tooltip carries
  a "tagged savings" line.
- **Pareto/Treemap**: a "Hide savings" toggle pill next to the group-by toggle
  (`.rfb__groupby-btn` styling). When active, a muted xs caption under the chart:
  "Excluding N savings/long-term-tagged categories" — exclusions are visible, never
  silent (same principle as the filter-support matrix).

### Implementation guide

1. `txn_filters.py` predicates + unit tests.
2. Thread `tag_ids` / `exclude_tag_keys` through the five endpoints + `report_service`.
3. Sankey savings routing + integration test.
4. `reportStore.ts` diffs; filter bar combobox; dimming entries.
5. Pareto/Treemap toggle + caption; `useSpendingGrouped` hook param.
6. `just quality`, `just typecheck`, hand-check Sankey totals.

### Test plan

- Predicate units: tagged/untagged/multi-tag categories; payee filter on parent rows
  vs split children (LEAF/PARENT_ROW interplay).
- Sankey integration: savings-tagged category outflow lands under the savings node and
  grand totals still reconcile (hand-computed dollars, existing test style).
- Exclude toggle changes Pareto totals by exactly the tagged categories' sum.

### Acceptance

Tag a category `savings` → it re-routes in Sankey and drops out of Pareto with the
toggle; tag filter works on Pareto/Treemap/Payees and dims elsewhere.

---

## R3 — Subscription detection + tracker (L, depends on R1)

**Goal**: find recurring charges automatically, let the user curate them, and give
subscriptions their own report — renewal cadence, monthly-equivalent cost, spend over
time — with the confirmed set feeding later phases (projection, payday exclusions).

### Backend design

**Migration `0004_subscription_candidates`:**

```python
class SubscriptionCandidate(Base):
    __tablename__ = "subscription_candidates"
    id:                 UUID pk
    budget_id:          UUID FK CASCADE, index
    payee_id:           UUID FK payees.id CASCADE   # UniqueConstraint(budget_id, payee_id)
    status:             String(20)   # 'proposed' | 'confirmed' | 'dismissed'
    cadence:            String(20)   # 'weekly'|'biweekly'|'monthly'|'quarterly'|'annual'
    cadence_override:   String(20), nullable   # user-set on confirm; wins over detected
    confidence:         Numeric(3, 2)
    last_amount:        Numeric(19, 4)   # most recent charge = current price
    avg_amount:         Numeric(19, 4)
    first_seen_date:    Date
    last_seen_date:     Date
    next_expected_date: Date             # last_seen + cadence days (override-aware)
    occurrence_count:   Integer
    source:             String(20), default 'detected'   # 'detected' | 'manual'
    detected_at / updated_at: DateTime(timezone=True)
```

**New `backend/src/igab/services/subscription_service.py`** — constants mirror
`transaction_matching_service.py` style:

```python
CADENCE_WINDOWS = {"weekly": (5, 9), "biweekly": (12, 16), "monthly": (26, 35),
                   "quarterly": (80, 100), "annual": (330, 400)}
CADENCE_DAYS    = {"weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 91, "annual": 365}
MIN_INTERVALS   = {"weekly": 3, "biweekly": 3, "monthly": 3, "quarterly": 2, "annual": 1}
INTERVAL_TOLERANCE     = 0.20   # gap within ±20% of median counts as regular
AMOUNT_DRIFT_TOLERANCE = 0.15   # consecutive amounts within ±15% count as consistent
ANNUAL_AMOUNT_TOLERANCE = 0.10  # annual: 1 interval allowed iff amounts within 10%
PROPOSE_THRESHOLD = 0.60        # no auto-confirm — curation is the point
LOOKBACK_MONTHS = 24
W_INTERVAL, W_AMOUNT, W_COUNT = 0.45, 0.35, 0.20
```

`detect(budget_id)`:

1. Query transactions: `NOT_DELETED, POSTED, LEAF, CASH_FLOW_ROW`, `amount < 0`,
   `payee_id IS NOT NULL`, `date >= today − 24 months`; exclude payees with
   `transfer_account_id`. Group in Python by `payee_id`; skip groups with < 2 rows.
2. Sort dates → day gaps. **Missed-occurrence normalization**: with running median
   `m`, for each gap compute `k = round(gap / m)`; if `k ≥ 2` and
   `|gap/k − m| ≤ INTERVAL_TOLERANCE · m`, replace the gap with `k` gaps of `gap/k`.
   A skipped month must not kill a monthly subscription.
3. Cadence = median of normalized gaps matched against `CADENCE_WINDOWS`; no window
   match → not a candidate.
4. Minimum evidence per `MIN_INTERVALS`; annual additionally requires amount agreement
   within `ANNUAL_AMOUNT_TOLERANCE` (a year-old budget only has two data points —
   leniency on count, strictness on amount).
5. `interval_score` = fraction of normalized gaps within ±20% of median.
   `amount_score` = fraction of consecutive |amount| pairs within ±15% — a price
   step-up followed by stability scores high; erratic amounts (groceries) score low.
   `confidence = 0.45·interval + 0.35·amount + 0.20·min(occurrences/6, 1)`, quantized
   to 0.01. Propose at `≥ PROPOSE_THRESHOLD`.
6. Upsert keyed on `(budget_id, payee_id)`: update metrics on `proposed` and
   `confirmed` rows, recomputing `next_expected_date = last_seen +
   CADENCE_DAYS[cadence_override or cadence]`. **Never** touch `dismissed` rows
   (remembered forever unless restored) or the cadence/amounts of `source='manual'`
   rows.
7. Return `{proposed: n_new, updated: n}`.

Runs on-demand only (tab mount + explicit Rescan) — household data volume makes this
sub-second; no scheduler.

**Curation semantics**: `confirm` sets status + optional `cadence_override` and
**adds the `subscription` system tag to the payee** (`tag_repo.add_payee_tag`) — the
tag is the durable, report-visible artifact; the candidate row holds analytics
metadata. `dismiss` on a previously confirmed row removes the tag. `restore` moves
dismissed → proposed. `manual` requires an existing payee and applies the tag
immediately.

**Endpoints** — new `api/v1/subscriptions.py` (+ report endpoint in `reports.py`):

| Endpoint | Body | Returns |
|---|---|---|
| `POST /{b}/subscriptions/detect` | — | `{proposed, updated}` |
| `GET /{b}/subscriptions?status=` | — | `list[SubscriptionOut]` |
| `POST /{b}/subscriptions/{id}/confirm` | `{cadence?}` | 204 |
| `POST /{b}/subscriptions/{id}/dismiss` | — | 204 |
| `POST /{b}/subscriptions/{id}/restore` | — | 204 |
| `POST /{b}/subscriptions/manual` | `{payee_id, cadence}` | `SubscriptionOut` 201 |
| `GET /{b}/reports/subscriptions?months=12` | — | `SubscriptionReportResponse` |

Schemas (`schemas/report.py` / `schemas/subscription.py`):

```python
class SubscriptionItem(BaseModel):
    id, payee_id, payee_name, cadence (effective), status, confidence, source
    last_amount, monthly_equivalent, annual_cost: Decimal
    last_renewal, next_expected: date
# monthly_equivalent: weekly ×52/12, biweekly ×26/12, monthly ×1,
# quarterly ÷3, annual ÷12 — quantize to cents.

class SubscriptionReportResponse(BaseModel):
    items: list[SubscriptionItem]        # confirmed only
    proposed: list[SubscriptionItem]     # feeds the review strip
    monthly_equivalent_total, annual_total: Decimal
    series: list[MonthSpend]             # {month, per_payee: dict[str, Decimal], total}
```

Retire the crude `is_recurring` heuristic in payee-analysis (payee active in 3+
months) — replace with `is_subscription` driven by confirmed candidates.

### UX design

New **Subscriptions** tab: `reportStore.ts` gains
`{ id: 'subscriptions', label: 'Subscriptions', group: 'insights' }`;
`TAB_FILTER_SUPPORT` entry all-false (the report owns its months selector, like
volatility). New `components/reports/SubscriptionsReport/` —
`SubscriptionsReport.tsx`, `ReviewStrip.tsx`, `SubscriptionsTable.tsx`, `.css`. Hooks:
report query in `api/reports.ts`; new `api/subscriptions.ts` with
detect/confirm/dismiss/restore/manual mutations invalidating
`['reports', 'subscriptions']`.

Layout top → bottom:

1. Standard report header — title, `ReportInfoButton` (modal explains detection
   honestly: 24-month lookback, cadence windows, why something can be missed,
   "detection proposes — you decide"), `ReportExportButton`.
2. **Review strip** — rendered only when `proposed.length > 0` (absent otherwise, not
   an empty box): a `.report-section` titled "Detected subscriptions · N to review".
   Rows use the curation pattern: payee name (sm, 600) · cadence pill (TargetBadge
   styling, `--color-info`) · confidence bar (`.match-modal__confidence` visual) ·
   "avg $14.99 · $14.99/mo" (tabular-nums) · last-seen date (xs muted) · cadence
   `<select>` (`.inspector-select` styling, prefilled with detected cadence) ·
   Confirm (accent) / Dismiss (surface). Quiet by design: no red badges, no count in
   the tab label — an invitation, not an alarm. Footer: muted "Dismissed (N)"
   disclosure expanding an inline list with Restore buttons.
3. **Metric cards** (`.report-metrics` + `MetricCard`): Monthly equivalent · Annual
   cost · Active count · Next renewal (payee + relative date).
4. **Chart**: stacked monthly `BarChart` of confirmed-subscription spend by payee over
   the selected months, `chartColors` palette, sankey-legend-style legend,
   `ChartTooltip`.
5. **Active table**: payee (chip-colored dot) · cadence · current price · monthly
   equivalent · last renewal · next expected (relative wording, `--text-secondary` —
   renewal proximity is information, not alarm). Row click → `DrillDownPanel` with
   `{kind: 'payee', scope: 'parent', payeeIds: [payee_id], startDate/endDate = report
   window}` — zero panel changes. Table header hosts "+ Add manually" (payee Combobox
   + cadence select in a small popover; SelectionSheet on mobile).

Empty states: never scanned → centered explainer + accent "Scan for subscriptions"
button; scanned and clean → "No recurring charges detected — nothing hiding in your
transactions." Mobile: table rows become cards (payee + price/cadence line + next
renewal), review-strip actions become full-width buttons, chart ~240px.

### Implementation guide

1. Migration `0004` + model + factory.
2. `subscription_service.py` detection + unit tests (the bulk of the phase's tests).
3. `subscription_repo.py` (upsert, list-by-status) + curation endpoints + tag
   integration; ownership tests.
4. Report endpoint + response assembly (series padded to `months`).
5. `api/subscriptions.ts` + report hook.
6. Tab registration; `SubscriptionsReport` skeleton with metric cards + chart.
7. `ReviewStrip` + dismissed disclosure; `SubscriptionsTable` + drill-down; manual-add
   popover.
8. Empty states, mobile cards, info modal, export; retire `is_recurring`.
9. `just quality`, `just typecheck`, full suite, 9-theme + mobile pass.

### Test plan (exhaustive — amount-adjacent)

Detection: clean monthly ×6 → proposed, high confidence; monthly with one missed month
→ still monthly (normalization); price increase mid-stream (9.99 → 12.99, stable
after) → survives; erratic amounts → below threshold; annual ×2 within 10% →
proposed; annual ×2, 20% apart → rejected; biweekly/monthly boundary (16- vs 26-day
gaps); below `MIN_INTERVALS` → no candidate; transfer payees excluded;
pending/deleted/split-parent rows excluded.
Curation: confirm applies tag / dismiss removes it / restore works; dismissed never
resurrected by re-detect; manual rows never overwritten; re-detect updates confirmed
metrics + `next_expected_date`.
Math: monthly-equivalent conversion table incl. cent rounding; report totals = sum of
items; series months padded.
Ownership 404s on all endpoints.

### Acceptance

Seed realistic data → scan proposes plausible subscriptions; confirm/dismiss/restore
flows work with toasts; confirming tags the payee (visible on PayeesPage); report
totals reconcile with drill-down transaction lists; themes + mobile pass.

---

## R4 — Anomaly detection (S, independent — can land anytime)

**Goal**: surface category-months that are far outside that category's own baseline,
in plain language, with guard rails so the report stays trustworthy (no z-score noise
from small or near-constant categories).

### Backend design

No new tables. `GET /{b}/reports/anomalies?months=12&threshold=2.0` in `reports.py`;
computation in `report_service.py` reusing the volatility monthly-aggregation Polars
pipeline (same query shape: `NOT_DELETED, POSTED, LEAF`, outflows, excluding the
current partial month).

Per category-month: leave-one-out baseline — mean/std over the window **excluding that
month**; `z = (actual − mean) / std`. Emit rows where `|z| ≥ threshold` AND all guard
rails pass:

- `months_of_history ≥ 6`
- `std ≥ 5.00` (kills near-constant categories where a $2 wobble is 4σ)
- `|actual − mean| ≥ 25.00` (absolute floor kills small-dollar noise)

Plain z + guard rails chosen over robust MAD for consistency with the volatility stats
users already see; the guards do the robustness work at this data scale.

```python
class AnomalyItem(BaseModel):
    category_id, category_name, category_group_name
    month: date
    actual, baseline_mean, baseline_std: Decimal
    z_score: float
    direction: Literal['high', 'low']
    history: list[MonthTotal]    # 12 points for the sparkline
class AnomalyResponse(BaseModel):
    items: list[AnomalyItem]     # sorted by |z| desc
```

### UX design

New **Anomalies** tab (`{ id: 'anomalies', label: 'Anomalies', group: 'insights' }`,
filters all-false, own months selector). New `components/reports/AnomaliesReport/`.

A single `.report-section` list grouped under month subheadings. Each row: category +
group (xs muted) · plain-language sentence **"$412 vs usual $145"** (tabular-nums;
z-score relegated to a muted suffix "z = 3.1" for the technical reader) ·
right-aligned ~120×32 sparkline (recharts `LineChart`, `--text-muted` stroke,
`ReferenceDot` on the anomalous month in the direction color). Direction color on the
actual amount only: high → `--color-negative`; low → `--color-info` (spending far
less can mean a missed bill — not automatically good, so never green).

Sensitivity: three-pill toggle (Strict z≥3 / Normal z≥2.5 / Sensitive z≥2,
`.rfb__groupby-btn` styling) mapped to `threshold` — no raw number input. Row click →
`DrillDownPanel` `{kind: 'category', scope: 'leaf', categoryIds, startDate/endDate =
that month}`.

**The empty state is the hero**: lucide `CheckCircle2` in `--color-positive` +
"Spending is within normal ranges across all categories" — deliberately reassuring.

### Implementation guide

1. `report_service.anomalies()` on the volatility pipeline + schemas + endpoint.
2. Unit/integration tests (below).
3. Hook in `api/reports.ts`; tab registration.
4. `AnomaliesReport` rows + sparklines + sensitivity toggle + drill-down + empty state.
5. Info modal (method + guard rails, honestly), export; quality gates; theme pass.

### Test plan

Hand-computed z on a seeded series; leave-one-out correctness (anomalous month
excluded from its own baseline); each guard rail suppressed individually (5-month
history / $4 std / $20 deviation); current partial month excluded; both directions;
threshold param honored.

### Acceptance

Seeded outlier month appears with correct sentence and sparkline; clean data shows the
reassuring empty state; sensitivity toggle changes the item set.

---

## R5 — Payday-effect panel (S, soft-depends R3, explicitly cuttable)

**Goal**: answer "do we spend more right after payday?" honestly — as an event study,
not a correlation gimmick.

Raw cross-correlation (income series × spending series at lag k) is statistically
fragile with one household's data and unreadable for users. Reframed: for each income
event, measure average daily spending in the days after it, against baseline.

### Backend design

`GET /{b}/reports/payday-effect?window=14` (window bounds 7–30).

- Income events: posted inflows ≥ P75 of trailing-12-month inflow amounts (fallback
  floor $200) on `CASH_FLOW_ROW` parent rows.
- For days 0…window after each event: average daily outflow, **excluding
  subscription-tagged payees and scheduled-transaction materializations** — otherwise
  the chart just rediscovers that rent is due on the 1st.
- Baseline: overall mean daily outflow over the same period with the same exclusions.
- Response: `{days: [{offset, avg_spend: Decimal}], baseline_daily: Decimal,
  event_count: int}`.

### UX design

Not a tab — a second `.report-section` inside the existing **Day Patterns** tab, below
the weekday chart: `BarChart` (x = days since payday 0–14, y = avg daily spend);
dashed `ReferenceLine` at baseline labeled "typical day"; bars above baseline tinted
`--color-warning` at low mix, others neutral. Caption (xs muted): "Excludes
subscriptions and scheduled bills · based on N income events." The Day Patterns info
modal is expanded to cover both panels and states the limits plainly.

**Cut criterion**: if dogfooding shows a flat profile after the exclusions, delete the
panel. This is written down so the decision doesn't need relitigating.

### Implementation guide

1. `report_service.payday_effect()` + endpoint + schema.
2. Tests (below).
3. Panel in `DayPatternsChart` (or sibling component in the same tab), caption, info
   modal update.
4. Quality gates; theme pass.

### Test plan

Synthetic payday spike on days +1..3 detected above baseline; subscription exclusion
changes the profile; `event_count` correct; window bounds enforced.

### Acceptance

Panel renders under Day Patterns with honest caption; flat data looks flat (no
manufactured drama).

---

## R6 — Cash projection fan chart (M, soft-depends R3)

**Goal**: "where is our balance heading?" — deterministic scheduled/subscription
events plus honest uncertainty bands from historical spending, with "when do we go
negative" as the headline question.

### Backend design

`GET /{b}/reports/cash-projection?days=90` (allowed 30/60/90/180) in `reports.py`;
computation in `report_service.py`.

- **Start balance**: sum of on-budget account balances (reuse
  `AccountRepository.get_balance` semantics — same as net worth).
- **Deterministic layer**: expand `ScheduledTransaction` occurrences over the horizon,
  **reusing the recurrence stepping in `scheduled_transaction_service.py`
  (`calculate_next`) — do not reimplement**; plus confirmed subscriptions stepped from
  `next_expected_date` at `CADENCE_DAYS[effective cadence]` with `last_amount`.
  Dedup: skip a subscription if a ScheduledTransaction with the same `payee_id`
  exists (would double-count). Pre-R3 the endpoint simply returns scheduled-only.
- **Stochastic layer**: trailing 180 days of posted, `PARENT_ROW`, `CASH_FLOW_ROW`
  daily net flow, minus transactions of deterministic payees. Bootstrap 500 paths:
  for each future date, sample with replacement a historical daily net **from the same
  weekday bucket** (weekend ≠ weekday spending); cumsum per path; add the
  deterministic cumulative to every path; per-day percentiles P10/25/50/75/90.
  Bootstrap over analytic √t scaling because daily spend is skewed and zero-inflated.
- **Seed `numpy.random.default_rng` with a stable hash of (budget_id, today, days)**
  — same-day responses are reproducible and testable. (numpy arrives with Polars; add
  it explicitly to `backend/pyproject.toml` if importing it directly, or compute
  percentiles in Polars to avoid the direct dependency.)

```python
class CashProjectionResponse(BaseModel):
    start_balance: Decimal
    points: list[ProjectionPoint]   # {date, p10, p25, p50, p75, p90, deterministic: Decimal}
    events: list[ProjectionEvent]   # {date, label, amount: Decimal, source: 'scheduled'|'subscription'}
    goes_negative_date: date | None # first date with P10 < 0
```

### UX design

New **Projection** tab (`{ id: 'projection', label: 'Projection', group: 'cashflow' }`,
filters all-false). New `components/reports/ProjectionReport/`.

- Top: horizon pills (30/60/90/180 days, `.rfb__groupby-btn` styling) + two
  `MetricCard`s — "Projected balance" (P50 at horizon end) and "Range" (P10–P90).
- Fan chart: `ComposedChart`; each point carries `band_outer: [p10, p90]` and
  `band_inner: [p25, p75]`; two `<Area>` components with array dataKeys (recharts
  range-area) in accent at ~10% / ~20% opacity via `color-mix`; solid accent P50
  `<Line>`; dashed `--text-muted` deterministic-only `<Line>`;
  `<ReferenceLine y={0}>` in `--color-negative` **only when** `goes_negative_date` is
  set (meaning over decoration); `<ReferenceDot>` markers for events ≥ $100.
- If `goes_negative_date`: one calm callout row above the chart —
  `background: color-mix(in srgb, var(--color-warning) 10%, var(--bg-secondary))` —
  "In the low scenario, balance could go negative around Aug 14." One sentence, not a
  red banner.
- Below: "Upcoming events" list — date · payee · amount · source pill (scheduled /
  subscription, TagChip styling).
- Info modal: what is deterministic vs simulated, and that projections improve once
  subscriptions are confirmed.
- Mobile: chart ~240px, tap tooltips, events list becomes the primary surface.

### Implementation guide

1. Deterministic expansion (scheduled + subscriptions + dedup) as a pure, separately
   testable function.
2. Bootstrap sampler with seeded RNG; percentile extraction.
3. Endpoint + schemas; hook; tab registration.
4. `ProjectionReport`: pills, metric cards, fan chart, events list, callout.
5. Info modal, export, empty/sparse-history handling (< 30 days of history → widen
   bands honestly and say so in the modal); quality gates; theme + mobile pass.

### Test plan

Seeded determinism (two same-day calls → identical); deterministic-only correctness
with zero stochastic history; scheduled+subscription dedup by payee; percentile
monotonicity (p10 ≤ p25 ≤ p50 ≤ p75 ≤ p90 for every day); `goes_negative_date` =
first P10 < 0; weekday stratification (weekend-only spender produces different weekend
sampling pool); horizon bounds validation.

### Acceptance

Fan renders with plausible bands; scheduled bills appear as dots on the deterministic
line; zero-crossing produces the calm callout and red zero-line; identical response on
refresh (same day).

---

## R7 — Debt data model & amortization engine (M, independent; pairs with Phase 3 Advanced Accounts)

**Goal**: a first-class `Debt` concept that can either point at an existing loan
Account ("managed" — balance and payment history come from the real ledger) or stand
completely alone ("unmanaged"/passive — the user enters balance/rate by hand and,
optionally, links a budget category so that category's spending doubles as the debt's
payment history, without ever creating a full Account). This phase builds the data
model and math only; **R8** builds the sidebar/detail-page UI on top of it, and **R9**
adds a consolidated cross-debt Reports tab.

This directly supersedes the checklist's Phase 3 "Advanced Accounts: Loan accounts
with amortization schedule" line — that work happens here, generalized to cover debts
that were never meant to be full Accounts (a private loan from family, a mortgage you
don't want a full transaction ledger for). It also supersedes the earlier version of
this roadmap's `loan_details`-on-Account sketch.

### Backend design

**Migration `0005_debts`:**

```python
class Debt(Base):
    __tablename__ = "debts"
    id:                 UUID pk
    budget_id:          UUID FK budgets.id CASCADE, index
    name:               String(100), nullable=False
    debt_type:          String(30)   # 'mortgage'|'auto'|'student'|'personal'|'credit_card'|'medical'|'other'
    linked_account_id:  UUID FK accounts.id ondelete=SET NULL, nullable=True, unique=True
        # present => "managed": balance + payment history derive from this account's ledger
        # null    => "unmanaged": balance is manual_balance; payments come from a linked
        #            category (below) or manual snapshots
    manual_balance:     Numeric(19, 4), nullable=True   # authoritative only when linked_account_id IS NULL
    interest_rate:      Numeric(7, 4), nullable=False   # annual percent, e.g. 6.2500
    minimum_payment:    Numeric(19, 4), nullable=False  # contractual payment — drives the baseline schedule
    compounding:        String(20), default='monthly'
    origination_date:   Date, nullable=True
    original_principal: Numeric(19, 4), nullable=True
    is_deleted:         Boolean, default=False
    created_at / updated_at: DateTime(timezone=True)

class DebtBalanceSnapshot(Base):
    __tablename__ = "debt_balance_snapshots"    # unmanaged debts only
    id:       UUID pk
    debt_id:  UUID FK debts.id CASCADE, index
    date:     Date, nullable=False
    balance:  Numeric(19, 4), nullable=False
    source:   String(20)   # 'initial' | 'manual'
    created_at: DateTime(timezone=True)
    # UniqueConstraint(debt_id, date) — one snapshot per day
```

`Category` gains a new nullable FK:

```python
linked_debt_id: Mapped[uuid.UUID | None] = mapped_column(
    FK("debts.id", ondelete="SET NULL"), nullable=True)
```

mirroring the existing `linked_account_id` pattern used today for credit-card payment
categories (`backend/src/igab/db/models.py:209`). **Mutual exclusivity is enforced at
the service layer**, not a DB constraint — keeps the migration simple: a category may
carry `linked_account_id` OR `linked_debt_id`, never both; 422 on the category-update
endpoint if both would end up set. When a category is linked to a debt, its outflow
transactions (`NOT_DELETED, POSTED, LEAF, CASH_FLOW_ROW`, `amount < 0`) are read as
payments toward that debt — this is the mechanism that lets an unmanaged debt (no bank
account at all) still have a real payment history.

**New `backend/src/igab/services/debt_math.py`** — pure, no I/O, same Decimal-loop
shape used throughout this roadmap for amount-critical calculations:

```python
def amortization_schedule(balance: Decimal, annual_rate: Decimal, payment: Decimal,
                           start_date: date, cap_months: int = 600) -> AmortizationResult:
    monthly_rate = annual_rate / 100 / 12
    schedule = []
    for month in range(cap_months):
        interest = quantize_cents(balance * monthly_rate)
        if payment <= interest and balance > 0:
            return AmortizationResult(schedule=schedule, never_pays_off=True,
                                       payoff_date=None, total_interest=sum(m.interest_paid for m in schedule))
        principal = min(payment - interest, balance)   # final-payment clamp
        balance -= principal
        schedule.append(AmortizationMonth(month_index=month, date=..., balance=balance,
                                           principal_paid=principal, interest_paid=interest))
        if balance <= 0:
            return AmortizationResult(schedule=schedule, never_pays_off=False,
                                       payoff_date=schedule[-1].date,
                                       total_interest=sum(m.interest_paid for m in schedule))
    return AmortizationResult(schedule=schedule, never_pays_off=True, payoff_date=None,
                               total_interest=sum(m.interest_paid for m in schedule))  # exceeded cap
```

Every step is cent-quantized; `sum(principal_paid) == starting_balance` must hold
exactly whenever the loan pays off (test plan below).

**Resolving balance + payment history** (new `services/debt_service.py`):

```python
async def get_debt_balance(debt: Debt) -> Decimal:
    if debt.linked_account_id:
        return await account_repo.get_balance(debt.linked_account_id)   # existing net-worth logic
    return debt.manual_balance

async def get_recent_monthly_payments(debt: Debt, months: int = 6) -> list[Decimal]:
    if debt.linked_account_id:
        # trailing month-end balance deltas on the linked account (paydown per month) —
        # reuses the same per-account monthly balance derivation as net_worth_history
        ...
    elif category := await category_repo.get_by_linked_debt(debt.id):
        # trailing monthly sums of that category's outflow transactions
        ...
    else:
        # sparse manual snapshots: balance deltas between consecutive snapshots,
        # spread evenly across the months each pair spans
        ...
    # every path: floor each month at 0 — a balance increase is not a negative payment
```

**Live payoff projection** — this is the "given the recent transactions/balance"
behavior the user asked for, distinct from the contractual schedule:

```python
def project_payoff(current_balance: Decimal, annual_rate: Decimal,
                    recent_payments: list[Decimal]) -> date | None:
    if len(recent_payments) < 2:
        return None   # not enough history — pill falls back to the baseline/contractual date
    avg_payment = mean(p for p in recent_payments if p > 0)
    result = amortization_schedule(current_balance, annual_rate, avg_payment, today)
    return None if result.never_pays_off else result.payoff_date
```

The **baseline** payoff date always uses `debt.minimum_payment` (the contractual
schedule); the **live** date uses trailing actual payment velocity. Both are surfaced
to the user — one is never silently substituted for the other (same honesty
principle as the anomaly/payday-effect sections above).

**Net worth correctness**: unmanaged debts are real liabilities and must not vanish
from net worth just because they aren't Accounts. `report_service.net_worth_history()`
gains `unmanaged_debt_total = sum(get_debt_balance(d) for d in unmanaged debts)`,
subtracted alongside `total_liabilities`; `NetWorthResponse` gains a top-level
`unmanaged_debt_total: Decimal` field so the existing per-account breakdown stays
accurate and this new bucket is visible and independently testable, not folded in
silently. Managed debts need no such addition — their linked Account is already
counted, and double-counting must be tested against explicitly (test plan below).

**Endpoints** — new `api/v1/debts.py` + `schemas/debt.py`, registered in `router.py`.
All ownership-scoped.

| Endpoint | Body | Returns |
|---|---|---|
| `GET /{b}/debts` | — | `list[DebtOut]` (name, type, mode, resolved balance, rate, baseline payoff date, live payoff date) |
| `POST /{b}/debts` | `{name, debt_type, interest_rate, minimum_payment, compounding?, linked_account_id? \| manual_balance?, origination_date?, original_principal?}` | `DebtOut` 201 |
| `PATCH /{b}/debts/{id}` | partial of the above | `DebtOut` |
| `DELETE /{b}/debts/{id}` | — | 204 |
| `POST /{b}/debts/{id}/balance-snapshots` | `{date?, balance}` | `DebtBalanceSnapshotOut` 201 — 422 if `linked_account_id` is set |
| `GET /{b}/debts/{id}/amortization?extra_payment=&from=now\|origination` | — | `AmortizationResponse` (baseline schedule, with-extra schedule, live-pace payoff date, history points when `from=origination`) |
| `PUT /{b}/categories/{id}/link-debt` | `{debt_id: UUID \| null}` | `CategoryOut` — 422 if the category already has `linked_account_id` |

### Implementation guide

1. Migration `0005_debts` (`Debt`, `DebtBalanceSnapshot`, `Category.linked_debt_id`) +
   models + factories.
2. `debt_math.py` + exhaustive unit tests (below) — before any endpoint work.
3. `debt_repo.py` (`BaseRepository[Debt]` + snapshot helpers) + `debt_service.py`
   (balance resolution, payment-history derivation, live projection).
4. `api/v1/debts.py` + schemas; category `link-debt` endpoint + mutual-exclusivity
   validation.
5. `net_worth_history()` addition + `NetWorthResponse.unmanaged_debt_total`;
   integration test that net worth reconciles with an unmanaged debt present.
6. `just quality`, `just test-backend`.

### Test plan (exhaustive — pure amount math + money correctness)

- `debt_math`: hand-computed 3-iteration schedule vs known-good values; final-payment
  clamp (never negative); `payment == interest` and `payment < interest` →
  `never_pays_off`; extra payment reduces months/interest by hand-checked deltas;
  **zero cent drift** — `sum(principal_paid) == starting_balance` exactly whenever the
  loan pays off.
- Balance resolution: managed → matches `AccountRepository.get_balance`; unmanaged →
  matches `manual_balance`.
- Payment-history derivation: managed (account monthly deltas), unmanaged + linked
  category (category monthly sums), unmanaged + snapshots-only (interpolated deltas),
  unmanaged + nothing (empty list, live projection returns `None`).
- Live projection: `< 2` data points → `None`; average-payment case matches a
  hand-computed amortization; payment ≤ interest → `never_pays_off` on the live
  projection too (no fabricated date).
- Mutual exclusivity: category PATCH with both `linked_account_id` and
  `linked_debt_id` set → 422; `link-debt` 422s if the category already has
  `linked_account_id`.
- Net worth: seeded unmanaged debt appears in `unmanaged_debt_total` and reduces net
  worth by exactly its balance; a managed debt is **not** double-counted (present only
  via its Account) — an explicit regression test, since this is the easiest way for
  this phase to silently corrupt an existing, already-audited number.
- Ownership 404s on every endpoint; snapshot POST on a managed debt → 422.

### Acceptance

Create a managed debt linked to an existing loan account and an unmanaged debt with a
manual balance + linked category; both resolve balance and payment history correctly;
net worth includes the unmanaged debt exactly once; amortization math checks out
against an external amortization calculator.

---

## R8 — Debts sidebar & detail page (M–L, depends on R7)

**Goal**: give debts the same first-class standing as Accounts — a sidebar section, a
detail page per debt with the amortization schedule, a paydown/interest chart, and a
live payoff-date pill — working the same way for managed and unmanaged debts. This is
the UI the user asked for directly: "a debt section in the left sidebar with each
listed like the bank accounts... a table that shows the pay off/amortization
schedule, a chart... and a pill... that indicates what the current payoff date is."

### UX design

**Sidebar** (`frontend/src/components/layout/Sidebar/Sidebar.tsx`): a new
`sidebar__debt-group` section below the account groups, mirroring the existing
account-group rendering exactly — a `groupDebts()` helper analogous to the existing
`groupAccounts()` (`Sidebar.tsx:26`), grouped by `debt_type`. Each row: name, resolved
balance (`tabular`, same negative-red convention already used for accounts —
`Sidebar.tsx:188`), a small 6px mode dot (accent = managed, muted = unmanaged — a
dot, not a badge; kept quiet per the calm-by-default principle). Click →
`navigate('/debts/:debtId')` (mirrors `handleAccountClick`, `Sidebar.tsx:89`); a
header row → `/debts` (all-debts overview, mirrors the existing `/accounts` link at
`Sidebar.tsx:151`).

**Routing** (`frontend/src/App.tsx`, alongside the existing `/accounts` routes at
lines 71–72): add
`<Route path="/debts" element={<DebtsOverviewPage />} />` and
`<Route path="/debts/:debtId" element={<DebtPage />} />` inside `MainLayout`.

**`DebtsOverviewPage`** (new, mirrors `AccountsOverviewPage`): a simple list/grid of
debt cards (name, type, balance, rate, payoff date) — the landing page when no
specific debt is selected.

**`DebtPage`** (new `pages/DebtPage/DebtPage.tsx` + `.css`, structurally parallel to
`pages/AccountPage/AccountPage.tsx`):

- **Header**: debt name, `debt_type` badge (`TargetBadge` styling), mode badge
  ("Managed" / "Unmanaged" — muted, informational, not a status color), a `Settings`
  gear icon (lucide, same icon `AccountPage.tsx` already imports) →
  `DebtSettingsModal` (create/edit: name, type, rate, minimum payment, compounding,
  and the mode switch — pick a linked account **or** enter a manual balance and
  optionally link a category; the UI must make the mutual exclusivity obvious, not
  just enforce it server-side).
- **Center payoff-date pill** — the visual centerpiece the user asked for: a large,
  centered pill, heavier than `TargetBadge` (closer to the weight of the planned "TBA
  hero" element noted elsewhere in CHECKLIST.md's budget-page backlog — reuse that
  visual register once it exists, or a comparably prominent treatment now). Primary
  text: the **live** payoff date ("Paid off around Mar 2034"); secondary muted line
  beneath: "Contractual: Jan 2041" when the two differ. If `never_pays_off` on either
  schedule: the pill switches to a warning-tinted state ("Current payments won't pay
  this off — increase your payment"). If no live projection exists yet (fewer than 2
  payment data points): the pill shows only the contractual date with a muted hint
  ("Add payment history for a live estimate") — never fabricates a live number from
  insufficient data.
- **Metric row** (`MetricCard`s): current balance · interest rate · total interest
  remaining (baseline) · months remaining (baseline).
- **Paydown + interest chart**: `ComposedChart` — balance `<Line>` over a stacked
  cumulative principal/interest `<Area>` pair (interest in `--color-negative` tint,
  principal in accent tint — the shrinking interest share is the story, same visual
  language planned for this chart throughout the roadmap). **Now / Beginning toggle**
  (`.rfb__groupby-btn` pair): "Now" plots only the future baseline projection from
  today to payoff; "Beginning" prepends the actual historical balance (from
  `origination_date`/snapshots for unmanaged, from account monthly history for
  managed) up to today, then continues into the same projected curve. The historical
  segment renders solid, the projected segment renders dashed, with a
  `<ReferenceLine x={today} label="Today">` marking the join — visually unambiguous
  about what's fact and what's forecast. A second `<ReferenceLine>` marks the **live**
  projected payoff date distinctly from where the baseline curve naturally ends, so
  the pill's headline number is traceable on the chart.
- **What-if**: "Extra monthly: $___" input (currency, debounced refetch against
  `?extra_payment=`), overlaying an accelerated dashed curve and a `--color-positive`
  result line: "+$100/mo → paid off 14 months sooner · $2,310 interest saved."
- **Amortization schedule table**: month, payment, principal, interest, remaining
  balance — paginated (match whatever pagination convention `TransactionTable` already
  uses, for consistency).
- **Unmanaged-only affordances**: an "Update balance" button opening a small form
  (balance + optional backdated date, defaulting to today) that posts a snapshot; if
  no category is linked, a prompt — "Link a budget category to track real payments" —
  opens a category picker (reuses `Combobox`) and calls
  `PUT /categories/{id}/link-debt`.
- **Managed-only affordance**: a "View account register" link to
  `/accounts/:accountId`.
- **Empty/setup state**: creating a debt from the sidebar's "+" opens
  `DebtSettingsModal` directly — no intermediate empty page.
- **Mobile**: header stacks, the pill stays centered and full-width, metric cards wrap
  2-up, chart height ~240px, the schedule table becomes stacked cards (date · payment
  · principal/interest split · balance).

### Implementation guide

1. `frontend/src/api/debts.ts` (React Query hooks: list, get, create, update, delete,
   snapshot, amortization, category link-debt).
2. Sidebar section + routes + `DebtsOverviewPage`.
3. `DebtPage` skeleton: header, metric row, empty/setup states.
4. Payoff-pill component (isolated even though it's used nowhere else — keep the
   never-pays-off / no-history states independently testable).
5. Paydown chart with Now/Beginning toggle + what-if overlay.
6. Amortization table.
7. `DebtSettingsModal` (mode switch, linked account/category pickers, mutual-
   exclusivity messaging).
8. "Update balance" flow; category-link prompt.
9. `just typecheck`; 9-theme + mobile pass.

### Test plan

Frontend: `just typecheck` clean; manual verification per the cross-cutting quality
bar (no automated frontend test suite exists for reports/accounts today — a
pre-existing gap, not specific to this phase). Backend surface is already covered by
R7's test plan; this phase's only new backend logic is the amortization endpoint's
`from=origination` branch, which needs one integration test confirming the historical
segment matches actual account/snapshot data before "today" and the amortization
formula after.

### Acceptance

A managed debt and an unmanaged debt both show correctly in the sidebar and detail
page; the payoff pill shows live vs. contractual dates distinctly and degrades
honestly with sparse data; the Now/Beginning toggle renders one coherent curve with a
clear "Today" marker; updating an unmanaged debt's balance updates the pill and chart;
linking a category starts feeding real payment history into both.

---

## R9 — Consolidated Debts report tab (S, depends on R7; benefits from R8)

**Goal**: a Reports-page view alongside the sidebar/detail pages the user asked for —
a cross-debt rollup with filtering, distinct from the per-debt deep-dive that now
lives in R8. "So how's all my debt doing" in one place.

### Backend design

`GET /{b}/reports/debts?debt_type=&mode=` in `reports.py`, backed entirely by R7's
`debt_service` — no new math, this is a rollup.

```python
class DebtsReportItem(BaseModel):
    debt_id, name, debt_type, mode: Literal['managed', 'unmanaged']
    current_balance, interest_rate: Decimal
    baseline_payoff_date: date | None
    live_payoff_date: date | None
    total_interest_remaining: Decimal
    never_pays_off: bool
class DebtsReportResponse(BaseModel):
    items: list[DebtsReportItem]
    total_balance, total_interest_remaining: Decimal
    balance_over_time: list[BalanceOverTimePoint]  # {date, per_debt: dict[str, Decimal], total}
                                                    # reuses each debt's R8 Beginning-mode history
```

### UX design

New **Debts** tab (`{ id: 'debts', label: 'Debts', group: 'financial' }`). Filter row:
debt type + managed/unmanaged toggle, styled like the existing filter-bar pills — a
standalone lightweight row rather than the full `ReportFiltersBar`, since dates don't
apply here. Layout: `MetricCard`s (total balance, total interest remaining, count);
stacked area chart of total debt balance over time by debt (`chartColors` palette,
reusing each debt's Beginning-mode history from R8); a sortable table (balance, rate,
baseline date, live date, interest remaining) whose row click **navigates to the
debt's detail page** (`/debts/:debtId`) rather than opening a `DrillDownPanel` — debts
aren't transaction-shaped, so the existing drill-down machinery doesn't apply, and the
doc says so explicitly rather than forcing the pattern where it doesn't fit.

### Implementation guide

1. `report_service.debts_report()` — thin aggregation over per-debt `debt_service`
   calls; endpoint + schema.
2. `api/reports.ts` hook; tab registration.
3. `DebtsReport.tsx`: metric cards, stacked chart, filterable table, row-click
   navigation to `/debts/:debtId`.
4. Info modal (clarifies this is a rollup — see the debt's own page for the schedule
   and pill), export; quality gates; theme pass.

### Test plan

Rollup totals equal the sum of R7's per-debt resolved balances/interest; type/mode
filters narrow the item list and totals correctly; a budget with zero debts shows a
clean empty state ("No debts tracked yet" + a link to add one).

### Acceptance

The tab shows every debt with correct rollup totals and filters; clicking a row lands
on the correct debt detail page.

---

## Deferred: external data infrastructure (decision shape only)

For inflation-adjusted trends and "if invested instead" (both deferred):

- One `external_series` table: `series_key String(30)`, `date Date`,
  `value Numeric(19, 6)`, `source String(50)`, `fetched_at`, PK `(series_key, date)`.
- Populated two ways: (a) a repo-bundled static CSV fallback loaded by migration
  (e.g. annual CPI-U through the release date); (b) a manual "Refresh external data"
  button in Settings hitting keyless public endpoints (BLS/FRED CSV for CPI, Stooq CSV
  for an S&P proxy). No background jobs, no API keys — self-hosted-friendly.
- Consuming reports must degrade gracefully to nominal values with a staleness badge
  when the series is missing or old.

Nothing else is committed now.

## Phasing

| Phase | Scope | Size | Depends on |
|---|---|---|---|
| R1 | Tags foundation: schema/CRUD, TagChip + theme slots, TagPicker, Settings panel, inspector section, payee column + bulk | M | — |
| R2 | Tag-aware semantics: predicates, Sankey savings node, Pareto/Treemap exclude toggle, tag filter bar | S | R1 |
| R3 | Subscription tracker: detection service, curation endpoints, review strip + report tab | L | R1 (system tag) |
| R4 | Anomaly detection tab | S | — (independent, can land anytime) |
| R5 | Payday-effect panel in Day Patterns | S | soft R3; **cuttable** |
| R6 | Cash projection fan chart tab | M | soft R3 (ships scheduled-only without it) |
| R7 | Debt data model & amortization engine (standalone `Debt` entity, managed/unmanaged, `Category.linked_debt_id`) | M | pairs with Phase 3 Advanced Accounts; independent of tags track |
| R8 | Debts sidebar section + per-debt detail page (schedule table, paydown chart, live payoff pill) | M–L | R7 |
| R9 | Consolidated Debts report tab (cross-debt rollup + filtering) | S | R7; benefits from R8 |
| Deferred | External data → inflation-adjusted / if-invested | — | `external_series` |

R4, R7, R8, and R9 parallelize with the tags track; R2 and R3 can proceed in parallel
after R1. Migration numbers are claims in landing order, not fixed identifiers.
