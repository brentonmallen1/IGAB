import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Copy, Link2, Pencil, Plus, RotateCcw, Trash2, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAppStore } from '../../../stores/appStore'
import { useGuideStore } from '../../../stores/guideStore'
import { confirmAsync } from '../../../stores/confirmStore'
import {
  useApplyPreview,
  useApplyTargets,
  useCategoryPlan,
  useCategoryPlans,
  useCreatePlan,
  useDeletePlan,
  useDuplicatePlan,
  useRenamePlan,
  useSavePlan,
  type ApplyEntry,
  type ApplyPreview,
  type PlanCadence,
} from '../../../api/categoryPlans'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useTargetsByBudget } from '../../../api/targets'
import { useDebouncedValue } from '../../../hooks/useDebouncedValue'
import { useFormatters } from '../../../hooks/useFormatters'
import { renderableCategoryIds } from '../../budget/budgetGroups'
import { AmountInput } from '../../common/AmountInput/AmountInput'
import { centsToInputString } from '../../../utils/amountExpression'
import { fromCents } from '../../../utils/money'
import { randomUUID } from '../../../utils/uuid'
import {
  CADENCES,
  derivePaycheckCount,
  draftToPayload,
  evenSplitCents,
  incomeTotalCents,
  monthlyPlannedCents,
  parseCentsField,
  parseDueDayField,
  paycheckIncomeCents,
  paycheckPlannedCents,
  payloadToDraft,
  resizePaychecks,
  seedCentsFromTarget,
  type DraftItem,
  type PlanDraft,
} from './plannerMath'
import './CategoryPlanner.css'

function blankItem(): DraftItem {
  return { id: randomUUID(), categoryId: null, name: '', dueDay: '', amount: '' }
}

/** The docJson a freshly loaded payload produces — the same pipeline the
 *  editor's serialization uses, so "dirty" never trips on key order. */
function baselineJson(payload: Parameters<typeof payloadToDraft>[0]): string {
  return JSON.stringify(draftToPayload(payloadToDraft(payload)))
}

/**
 * The category planner: paycheck columns, category rows, live totals.
 *
 * The draft (raw input strings) is the source of truth while mounted; it
 * autosaves on every change — debounced ~800ms for keystrokes, immediately
 * for structural edits (add/move/delete/import/resize) — and flushes on
 * unmount and plan switch. The math is `plannerMath.ts`, all of it.
 */
export function CategoryPlanner() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const activePlanId = useGuideStore((s) => s.activePlanId)
  const setActivePlanId = useGuideStore((s) => s.setActivePlanId)
  const { formatMoney } = useFormatters()

  const plansQuery = useCategoryPlans(budgetId)
  const plans = plansQuery.data ?? []
  const resolvedId =
    activePlanId && plans.some((p) => p.id === activePlanId) ? activePlanId : (plans[0]?.id ?? null)
  const planQuery = useCategoryPlan(budgetId, resolvedId)

  const createPlan = useCreatePlan(budgetId)
  const savePlan = useSavePlan(budgetId)
  const renamePlan = useRenamePlan(budgetId)
  const duplicatePlan = useDuplicatePlan(budgetId)
  const deletePlan = useDeletePlan(budgetId)

  // ── draft + autosave ──────────────────────────────────────────────────
  const [draftState, setDraftState] = useState<{ planId: string; draft: PlanDraft } | null>(null)
  const [lastSavedJson, setLastSavedJson] = useState('')
  const [saveFailed, setSaveFailed] = useState(false)
  const [flushTick, setFlushTick] = useState(0)

  // Hydrate when the loaded plan changes — the "adjusting state during
  // render" pattern, guarded by plan id so it settles in one extra pass.
  const loaded = planQuery.data
  if (loaded && draftState?.planId !== loaded.id) {
    setLastSavedJson(baselineJson(loaded.payload))
    setDraftState({ planId: loaded.id, draft: payloadToDraft(loaded.payload) })
    setSaveFailed(false)
  } else if (!loaded && resolvedId === null && draftState !== null) {
    setDraftState(null)
  }

  const draft = draftState?.planId === resolvedId ? draftState.draft : null
  const doc = useMemo(() => (draft ? draftToPayload(draft) : null), [draft])
  const docJson = useMemo(() => (doc ? JSON.stringify(doc) : ''), [doc])
  const dirty = docJson !== '' && docJson !== lastSavedJson

  // Snapshot for callbacks that outlive this render (unmount flush, the
  // debounced-save effect). Written in an effect, never during render.
  const latest = useRef({ docJson, planId: resolvedId, dirty })
  useEffect(() => {
    latest.current = { docJson, planId: resolvedId, dirty }
  })

  function saveCurrent(force = false) {
    const { docJson: json, planId, dirty: isDirty } = latest.current
    if (!planId || !isDirty || !json) return
    // One PUT at a time: a second in flight could land out of order and
    // mis-set the baseline. The settle effect below picks up remaining dirt.
    if (savePlan.isPending && !force) return
    savePlan.mutate(
      { planId, payload: JSON.parse(json) },
      {
        onSuccess: (_data, vars) => {
          // The baseline is what was SENT — anything typed while the request
          // flew keeps the draft dirty and the settle effect saves it next.
          setLastSavedJson(JSON.stringify(vars.payload))
          setSaveFailed(false)
        },
        onError: () => setSaveFailed(true),
      }
    )
  }

  // Structural edits (add/move/delete/import/resize) save straight away.
  useEffect(() => {
    if (flushTick > 0) saveCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flushTick])

  // Keystrokes save once they settle — and when an in-flight save lands,
  // isPending flipping re-runs this to sweep up anything typed meanwhile.
  const debouncedJson = useDebouncedValue(docJson, 800)
  useEffect(() => {
    if (savePlan.isPending) return
    if (debouncedJson && debouncedJson === latest.current.docJson) saveCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedJson, savePlan.isPending])

  // Flush on unmount (leaving the tab, the page, or the Guide entirely).
  useEffect(() => {
    return () => saveCurrent(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function update(mutator: (d: PlanDraft) => PlanDraft, opts?: { flush?: boolean }) {
    setSaveFailed(false)
    setDraftState((s) => (s ? { ...s, draft: mutator(s.draft) } : s))
    if (opts?.flush) setFlushTick((t) => t + 1)
  }

  function switchPlan(id: string) {
    if (id === resolvedId) return
    saveCurrent()
    setActivePlanId(id)
  }

  // ── header handlers ───────────────────────────────────────────────────
  function setCount(next: number) {
    if (next < 1 || next > 10) return
    update(
      (d) => {
        const { paychecks, moved } = resizePaychecks(d.paychecks, next, randomUUID)
        if (moved > 0) toast(`${moved} ${moved === 1 ? 'row' : 'rows'} moved to Paycheck ${next}`)
        return { ...d, countOverride: next, paychecks }
      },
      { flush: true }
    )
  }

  function setCadence(cadence: PlanCadence) {
    update(
      (d) => {
        // No override: the column count follows the cadence. With one, the
        // user's count stands and only the label changes.
        if (d.countOverride !== null) return { ...d, cadence }
        const target = derivePaycheckCount(cadence)
        const { paychecks, moved } = resizePaychecks(d.paychecks, target, randomUUID)
        if (moved > 0) toast(`${moved} ${moved === 1 ? 'row' : 'rows'} moved to Paycheck ${target}`)
        return { ...d, cadence, paychecks }
      },
      { flush: true }
    )
  }

  // ── empty / loading states ────────────────────────────────────────────
  if (!budgetId) return null
  if (plansQuery.isSuccess && plans.length === 0) {
    return (
      <div className="tool planner">
        <div className="planner__empty">
          <p className="planner__empty-lede">
            Lay your categories under the paychecks that pay for them: how much each check has to
            cover, which bills wait for the next one, and what is left of the month.
          </p>
          <button
            type="button"
            className="guide-link-button"
            onClick={() => createPlan.mutate({}, { onSuccess: (p) => setActivePlanId(p.id) })}
            disabled={createPlan.isPending}
          >
            <Plus size={12} aria-hidden /> Start a plan
          </button>
        </div>
      </div>
    )
  }
  if (!draft || !doc) return <div className="tool planner planner--loading">Loading plan…</div>

  const count = doc.paychecks.length
  const split = evenSplitCents(doc.monthly_income_cents, count)
  const planned = monthlyPlannedCents(doc)
  const incomeTotal = incomeTotalCents(doc)
  const leftToPlan = doc.monthly_income_cents - planned
  const drift = incomeTotal - doc.monthly_income_cents
  const money = (cents: number) => formatMoney(fromCents(cents))

  const saveStatus = savePlan.isPending
    ? 'Saving…'
    : saveFailed
      ? 'Couldn’t save'
      : dirty
        ? 'Unsaved changes'
        : 'Saved'

  return (
    <div className="tool planner">
      <PlanTabs
        plans={plans}
        activeId={resolvedId}
        onSwitch={switchPlan}
        onCreate={() => createPlan.mutate({}, { onSuccess: (p) => setActivePlanId(p.id) })}
        onRename={(name) => resolvedId && renamePlan.mutate({ planId: resolvedId, name })}
        onDuplicate={() =>
          resolvedId &&
          duplicatePlan.mutate({ planId: resolvedId }, { onSuccess: (p) => setActivePlanId(p.id) })
        }
        onDelete={async () => {
          const plan = plans.find((p) => p.id === resolvedId)
          if (!plan) return
          const ok = await confirmAsync({
            title: `Delete “${plan.name}”?`,
            message: 'The plan is a scratchpad — your budget’s categories are untouched.',
            confirmLabel: 'Delete plan',
            destructive: true,
          })
          if (ok) {
            deletePlan.mutate(plan.id, { onSuccess: () => setActivePlanId(null) })
          }
        }}
      />

      <div className="planner__header tool__grid">
        <label className="tool__field">
          <span>Monthly take-home</span>
          <AmountInput
            aria-label="Monthly take-home"
            className={
              Number.isNaN(parseCentsField(draft.monthlyIncome)) ? 'is-invalid' : undefined
            }
            value={draft.monthlyIncome}
            onValueChange={(v) => update((d) => ({ ...d, monthlyIncome: v }))}
            placeholder="0.00"
          />
        </label>
        <label className="tool__field">
          <span>Paid</span>
          <select
            aria-label="Pay cadence"
            value={draft.cadence}
            onChange={(e) => setCadence(e.target.value as PlanCadence)}
          >
            {CADENCES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <div className="tool__field">
          <span>Paychecks this month</span>
          <div className="planner__stepper" role="group" aria-label="Paycheck count">
            <button type="button" onClick={() => setCount(count - 1)} disabled={count <= 1}>
              −
            </button>
            <span className="tabular">{count}</span>
            <button type="button" onClick={() => setCount(count + 1)} disabled={count >= 10}>
              +
            </button>
          </div>
        </div>
        <div className="planner__header-actions">
          <span
            className={`planner__save-status ${saveFailed ? 'planner__save-status--failed' : ''}`}
            role="status"
          >
            {saveStatus}
            {saveFailed && (
              <button type="button" className="guide-link-button" onClick={() => saveCurrent()}>
                Retry
              </button>
            )}
          </span>
        </div>
      </div>

      <div className="planner__columns">
        {draft.paychecks.map((paycheck, pi) => {
          const income = paycheckIncomeCents(doc, pi)
          const colPlanned = paycheckPlannedCents(doc.paychecks[pi])
          const remaining = income - colPlanned
          const overridden = doc.paychecks[pi].income_override_cents !== null
          return (
            <section key={paycheck.id} className="planner__column surface surface--sunken">
              <header className="planner__column-head">
                <h3>Paycheck {pi + 1}</h3>
                <div
                  className={`planner__income ${overridden ? 'planner__income--overridden' : ''}`}
                >
                  <AmountInput
                    aria-label={`Paycheck ${pi + 1} income`}
                    className={
                      Number.isNaN(parseCentsField(paycheck.income)) ? 'is-invalid' : undefined
                    }
                    value={paycheck.income}
                    onValueChange={(v) =>
                      update((d) => ({
                        ...d,
                        paychecks: d.paychecks.map((p, i) => (i === pi ? { ...p, income: v } : p)),
                      }))
                    }
                    placeholder={centsToInputString(split[pi] ?? 0)}
                  />
                  {overridden && (
                    <button
                      type="button"
                      className="tool__icon-button"
                      aria-label="Back to the even split"
                      title="Back to the even split"
                      onClick={() =>
                        update((d) => ({
                          ...d,
                          paychecks: d.paychecks.map((p, i) =>
                            i === pi ? { ...p, income: '' } : p
                          ),
                        }))
                      }
                    >
                      <RotateCcw size={12} />
                    </button>
                  )}
                </div>
              </header>

              {paycheck.items.length > 0 && (
                <div className="planner__rows">
                  {paycheck.items.map((item) => (
                    <ItemRow
                      key={item.id}
                      item={item}
                      paycheckIndex={pi}
                      paycheckCount={count}
                      onChange={(next) =>
                        update((d) => ({
                          ...d,
                          paychecks: d.paychecks.map((p, i) =>
                            i === pi
                              ? {
                                  ...p,
                                  items: p.items.map((x) => (x.id === item.id ? next : x)),
                                }
                              : p
                          ),
                        }))
                      }
                      onRemove={() =>
                        update(
                          (d) => ({
                            ...d,
                            paychecks: d.paychecks.map((p, i) =>
                              i === pi
                                ? { ...p, items: p.items.filter((x) => x.id !== item.id) }
                                : p
                            ),
                          }),
                          { flush: true }
                        )
                      }
                      onMove={(to) =>
                        update(
                          (d) => ({
                            ...d,
                            paychecks: d.paychecks.map((p, i) => {
                              if (i === pi)
                                return { ...p, items: p.items.filter((x) => x.id !== item.id) }
                              if (i === to) return { ...p, items: [...p.items, item] }
                              return p
                            }),
                          }),
                          { flush: true }
                        )
                      }
                    />
                  ))}
                </div>
              )}

              <button
                type="button"
                className="guide-link-button tool__add"
                onClick={() =>
                  update(
                    (d) => ({
                      ...d,
                      paychecks: d.paychecks.map((p, i) =>
                        i === pi ? { ...p, items: [...p.items, blankItem()] } : p
                      ),
                    }),
                    { flush: true }
                  )
                }
              >
                <Plus size={12} aria-hidden /> Add a category
              </button>

              <dl className="planner__column-foot">
                <div>
                  <dt>Income</dt>
                  <dd className="tabular">{money(income)}</dd>
                </div>
                <div>
                  <dt>Planned</dt>
                  <dd className="tabular">{money(colPlanned)}</dd>
                </div>
                <div className={remaining < 0 ? 'planner__figure--over' : ''}>
                  <dt>Left</dt>
                  <dd className="tabular">{money(remaining)}</dd>
                </div>
              </dl>
            </section>
          )
        })}
      </div>

      <dl className="planner__summary surface surface--chrome">
        <div>
          <dt>Take-home</dt>
          <dd className="tabular">{money(doc.monthly_income_cents)}</dd>
        </div>
        {drift !== 0 && (
          <div className="planner__figure--drift">
            <dt>Paychecks add up to</dt>
            <dd className="tabular">
              {money(incomeTotal)} ({drift > 0 ? '+' : '−'}
              {money(Math.abs(drift))})
            </dd>
          </div>
        )}
        <div>
          <dt>Planned</dt>
          <dd className="tabular">{money(planned)}</dd>
        </div>
        <div className={leftToPlan < 0 ? 'planner__figure--over' : ''}>
          <dt>{leftToPlan < 0 ? 'Over by' : 'Left to plan'}</dt>
          <dd className="tabular">{money(Math.abs(leftToPlan))}</dd>
        </div>
      </dl>

      <ImportPanel
        budgetId={budgetId}
        linkedIds={
          new Set(
            draft.paychecks
              .flatMap((p) => p.items.map((i) => i.categoryId))
              .filter(Boolean) as string[]
          )
        }
        paycheckCount={count}
        onImport={(items, to) =>
          update(
            (d) => ({
              ...d,
              paychecks: d.paychecks.map((p, i) =>
                i === to ? { ...p, items: [...p.items, ...items] } : p
              ),
            }),
            { flush: true }
          )
        }
      />

      <ApplyPanel
        budgetId={budgetId}
        planId={resolvedId!}
        dirty={dirty}
        flush={saveCurrent}
        saving={savePlan.isPending}
        onApplied={(payload) => {
          setLastSavedJson(baselineJson(payload))
          setDraftState({ planId: resolvedId!, draft: payloadToDraft(payload) })
        }}
      />
    </div>
  )
}

// ── plan tabs ───────────────────────────────────────────────────────────────

function PlanTabs(props: {
  plans: { id: string; name: string }[]
  activeId: string | null
  onSwitch: (id: string) => void
  onCreate: () => void
  onRename: (name: string) => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const active = props.plans.find((p) => p.id === props.activeId)

  return (
    <div className="planner__tabs">
      <div className="guide-viewswitch" role="group" aria-label="Plans">
        {props.plans.map((p) =>
          editing !== null && p.id === props.activeId ? (
            <input
              key={p.id}
              className="planner__rename"
              aria-label="Plan name"
              value={editing}
              autoFocus
              onChange={(e) => setEditing(e.target.value)}
              onBlur={() => setEditing(null)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && editing.trim()) {
                  props.onRename(editing.trim())
                  setEditing(null)
                }
                if (e.key === 'Escape') setEditing(null)
              }}
            />
          ) : (
            <button
              key={p.id}
              type="button"
              className={`guide-viewswitch__button ${
                p.id === props.activeId ? 'guide-viewswitch__button--active' : ''
              }`}
              aria-pressed={p.id === props.activeId}
              onClick={() => props.onSwitch(p.id)}
            >
              {p.name}
            </button>
          )
        )}
        {props.plans.length < 20 && (
          <button
            type="button"
            className="guide-viewswitch__button"
            aria-label="New plan"
            title="New plan"
            onClick={props.onCreate}
          >
            <Plus size={12} aria-hidden />
          </button>
        )}
      </div>
      {active && (
        <div className="planner__tab-actions">
          <button
            type="button"
            className="tool__icon-button"
            aria-label={`Rename ${active.name}`}
            title="Rename"
            onClick={() => setEditing(active.name)}
          >
            <Pencil size={13} />
          </button>
          <button
            type="button"
            className="tool__icon-button"
            aria-label={`Duplicate ${active.name}`}
            title="Duplicate"
            onClick={props.onDuplicate}
          >
            <Copy size={13} />
          </button>
          <button
            type="button"
            className="tool__icon-button"
            aria-label={`Delete ${active.name}`}
            title="Delete"
            onClick={props.onDelete}
          >
            <Trash2 size={13} />
          </button>
        </div>
      )}
    </div>
  )
}

// ── one row ─────────────────────────────────────────────────────────────────

function ItemRow(props: {
  item: DraftItem
  paycheckIndex: number
  paycheckCount: number
  onChange: (next: DraftItem) => void
  onRemove: () => void
  onMove: (to: number) => void
}) {
  const { item } = props
  const amountBad = Number.isNaN(parseCentsField(item.amount))
  const dueBad = Number.isNaN(parseDueDayField(item.dueDay))
  return (
    <div className="planner__row">
      <div className="planner__row-name">
        {item.categoryId !== null && (
          <Link2 size={11} aria-label="Linked to a budget category" className="planner__link" />
        )}
        <input
          aria-label="Category name"
          value={item.name}
          readOnly={item.categoryId !== null}
          placeholder="Category"
          onChange={(e) => props.onChange({ ...item, name: e.target.value })}
        />
      </div>
      <input
        aria-label="Due day of month"
        className={`planner__due ${dueBad ? 'is-invalid' : ''}`}
        inputMode="numeric"
        value={item.dueDay}
        placeholder="Due"
        title="Due day of the month, 1–31"
        onChange={(e) => props.onChange({ ...item, dueDay: e.target.value })}
      />
      <AmountInput
        aria-label="Amount"
        className={`planner__amount ${amountBad ? 'is-invalid' : ''}`}
        value={item.amount}
        placeholder="0.00"
        onValueChange={(v) => props.onChange({ ...item, amount: v })}
      />
      {props.paycheckCount > 1 && (
        <select
          aria-label="Move to another paycheck"
          className="planner__move"
          value=""
          onChange={(e) => {
            if (e.target.value !== '') props.onMove(Number(e.target.value))
          }}
        >
          <option value="">⇄</option>
          {Array.from({ length: props.paycheckCount }, (_, i) => i)
            .filter((i) => i !== props.paycheckIndex)
            .map((i) => (
              <option key={i} value={i}>
                To Paycheck {i + 1}
              </option>
            ))}
        </select>
      )}
      <button
        type="button"
        className="tool__icon-button"
        aria-label={`Remove ${item.name || 'row'}`}
        onClick={props.onRemove}
      >
        <X size={13} />
      </button>
    </div>
  )
}

// ── pull in budget categories ───────────────────────────────────────────────

function ImportPanel(props: {
  budgetId: string
  linkedIds: Set<string>
  paycheckCount: number
  onImport: (items: DraftItem[], toPaycheck: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [destination, setDestination] = useState(0)
  const groups = useCategoryGroups(open ? props.budgetId : null)
  const categories = useCategories(open ? props.budgetId : null)
  const targets = useTargetsByBudget(open ? props.budgetId : null)

  const candidates = useMemo(() => {
    if (!groups.data || !categories.data) return []
    const renderable = renderableCategoryIds(groups.data, categories.data)
    return categories.data.filter(
      (c) =>
        renderable.has(c.id) &&
        c.linked_liability_id === null &&
        !c.is_archived &&
        !props.linkedIds.has(c.id)
    )
  }, [groups.data, categories.data, props.linkedIds])

  const targetByCategory = useMemo(
    () => new Map((targets.data ?? []).map((t) => [t.category_id, t])),
    [targets.data]
  )

  if (!open) {
    return (
      <div className="planner__panel-toggle">
        <button type="button" className="guide-link-button" onClick={() => setOpen(true)}>
          Pull in budget categories
        </button>
      </div>
    )
  }

  function importPicked() {
    const items: DraftItem[] = candidates
      .filter((c) => picked.has(c.id))
      .map((c) => {
        const seed = seedCentsFromTarget(targetByCategory.get(c.id))
        return {
          id: randomUUID(),
          categoryId: c.id,
          name: c.name,
          dueDay: '',
          amount: seed === null ? '' : centsToInputString(seed),
        }
      })
    props.onImport(items, destination)
    setPicked(new Set())
    setOpen(false)
  }

  return (
    <div className="planner__panel surface surface--sunken">
      <div className="planner__panel-head">
        <h4>Pull in budget categories</h4>
        <button
          type="button"
          className="tool__icon-button"
          aria-label="Close"
          onClick={() => setOpen(false)}
        >
          <X size={13} />
        </button>
      </div>
      {categories.isLoading || groups.isLoading ? (
        <p className="tool__hint">Loading categories…</p>
      ) : candidates.length === 0 ? (
        <p className="tool__hint">
          Every category the budget offers is already in this plan — or the budget has none yet.
        </p>
      ) : (
        <>
          <p className="tool__hint">
            Amounts start from each category’s monthly target where it has one; everything else
            starts blank.
          </p>
          <div className="planner__import-list">
            {candidates.map((c) => (
              <label key={c.id} className="planner__import-item">
                <input
                  type="checkbox"
                  checked={picked.has(c.id)}
                  onChange={(e) => {
                    const next = new Set(picked)
                    if (e.target.checked) next.add(c.id)
                    else next.delete(c.id)
                    setPicked(next)
                  }}
                />
                <span>{c.name}</span>
              </label>
            ))}
          </div>
          <div className="planner__panel-actions">
            <button
              type="button"
              className="guide-link-button"
              onClick={() => setPicked(new Set(candidates.map((c) => c.id)))}
            >
              Select all
            </button>
            <select
              aria-label="Which paycheck the rows go under"
              value={destination}
              onChange={(e) => setDestination(Number(e.target.value))}
            >
              {Array.from({ length: props.paycheckCount }, (_, i) => (
                <option key={i} value={i}>
                  Under Paycheck {i + 1}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="guide-link-button"
              disabled={picked.size === 0}
              onClick={importPicked}
            >
              <Plus size={12} aria-hidden /> Add {picked.size || ''}{' '}
              {picked.size === 1 ? 'category' : 'categories'}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ── apply to budget ─────────────────────────────────────────────────────────

const APPLY_COPY: Record<ApplyEntry['kind'], string> = {
  set_target: 'new monthly target',
  update_target: 'target updated',
  create_category: 'new category in “Planned”',
  skip_existing_type: 'keeps its existing target',
  skip_invalid_link: 'link no longer valid — skipped',
  skip_draft: 'unfinished row — skipped',
}

function ApplyPanel(props: {
  budgetId: string
  planId: string
  dirty: boolean
  saving: boolean
  flush: () => void
  onApplied: (payload: Parameters<typeof payloadToDraft>[0]) => void
}) {
  const [preview, setPreview] = useState<ApplyPreview | null>(null)
  const previewMutation = useApplyPreview(props.budgetId)
  const applyMutation = useApplyTargets(props.budgetId)
  const { formatMoney } = useFormatters()

  // A preview of an unsaved draft would describe the wrong document; wait for
  // the in-flight autosave, then ask.
  const pendingRef = useRef(false)
  useEffect(() => {
    if (pendingRef.current && !props.dirty && !props.saving) {
      pendingRef.current = false
      previewMutation.mutate(props.planId, { onSuccess: setPreview })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.dirty, props.saving])

  function openPreview() {
    if (props.dirty || props.saving) {
      pendingRef.current = true
      props.flush()
      return
    }
    previewMutation.mutate(props.planId, { onSuccess: setPreview })
  }

  function confirmApply() {
    applyMutation.mutate(props.planId, {
      onSuccess: (result) => {
        props.onApplied(result.plan.payload)
        setPreview(null)
        const bits = [
          result.targets_set + result.targets_updated > 0
            ? `${result.targets_set + result.targets_updated} target${
                result.targets_set + result.targets_updated === 1 ? '' : 's'
              } set`
            : null,
          result.categories_created > 0
            ? `${result.categories_created} categor${
                result.categories_created === 1 ? 'y' : 'ies'
              } created`
            : null,
        ].filter(Boolean)
        toast.success(bits.length ? bits.join(', ') : 'Nothing to apply')
      },
    })
  }

  const actionable = preview
    ? preview.targets_set + preview.targets_updated + preview.categories_created
    : 0

  if (!preview) {
    return (
      <div className="planner__panel-toggle">
        <button
          type="button"
          className="guide-link-button"
          onClick={openPreview}
          disabled={previewMutation.isPending}
        >
          Set targets on your budget…
        </button>
      </div>
    )
  }

  return (
    <div className="planner__panel surface surface--sunken">
      <div className="planner__panel-head">
        <h4>What applying this plan does</h4>
        <button
          type="button"
          className="tool__icon-button"
          aria-label="Close"
          onClick={() => setPreview(null)}
        >
          <X size={13} />
        </button>
      </div>
      <ul className="planner__apply-list">
        {preview.entries.map((entry, i) => (
          <li key={i} className={entry.kind.startsWith('skip') ? 'planner__apply--skip' : ''}>
            <span className="planner__apply-name">{entry.name || '(unnamed row)'}</span>
            <span className="planner__apply-what">
              {APPLY_COPY[entry.kind]}
              {entry.amount !== null && ` — ${formatMoney(entry.amount)}/mo`}
              {entry.existing_target_type && ` (${entry.existing_target_type.replace(/_/g, ' ')})`}
            </span>
          </li>
        ))}
      </ul>
      <div className="planner__panel-actions">
        <button type="button" className="guide-link-button" onClick={() => setPreview(null)}>
          Cancel
        </button>
        <button
          type="button"
          className="guide-link-button planner__apply-confirm"
          disabled={actionable === 0 || applyMutation.isPending}
          onClick={confirmApply}
        >
          <Check size={12} aria-hidden /> Apply to budget
        </button>
      </div>
    </div>
  )
}
