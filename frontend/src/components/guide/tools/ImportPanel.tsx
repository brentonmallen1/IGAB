import { useMemo, useState } from 'react'
import { Plus } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useTargetsByBudget } from '../../../api/targets'
import { renderableCategoryIds } from '../../budget/budgetGroups'
import { Dialog } from '../../common/Dialog/Dialog'
import {
  GroupedMultiSelect,
  type MultiSelectOption,
} from '../../common/GroupedMultiSelect/GroupedMultiSelect'
import { centsToInputString } from '../../../utils/amountExpression'
import { randomUUID } from '../../../utils/uuid'
import { seedCentsFromTarget, type DraftItem } from './plannerMath'

/**
 * "Pull in budget categories" — picking rows for the plan out of the budget.
 *
 * A dialog rather than a panel wedged into the page: the choice is a detour
 * from editing the plan, and on a phone `Dialog` makes it a sheet instead of
 * something that grows the page under your thumb. The list itself is
 * `common/GroupedMultiSelect`, so the categories arrive under their real
 * budget groups with search and per-group toggles — the flat, unsearchable
 * checkbox grid this replaces threw away the group structure it had already
 * fetched.
 */
export function ImportPanel(props: {
  budgetId: string
  linkedIds: Set<string>
  paycheckCount: number
  onImport: (items: DraftItem[], toPaycheck: number) => void
}) {
  const [open, setOpen] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [destination, setDestination] = useState(0)
  const groups = useCategoryGroups(open ? props.budgetId : null)
  const categories = useCategories(open ? props.budgetId : null)
  const targets = useTargetsByBudget(open ? props.budgetId : null)

  const candidates = useMemo(() => {
    if (!groups.data || !categories.data) return []
    const renderable = renderableCategoryIds(groups.data, categories.data)
    const groupOrder = new Map(groups.data.map((g) => [g.id, g.sort_order]))
    return categories.data
      .filter(
        (c) =>
          renderable.has(c.id) &&
          c.linked_liability_id === null &&
          !c.is_archived &&
          !props.linkedIds.has(c.id)
      )
      .sort(
        (a, b) =>
          (groupOrder.get(a.category_group_id) ?? 0) - (groupOrder.get(b.category_group_id) ?? 0) ||
          a.sort_order - b.sort_order
      )
  }, [groups.data, categories.data, props.linkedIds])

  // Group name carried on every option, so the list renders the budget's own
  // headers rather than one undifferentiated column of names.
  const options = useMemo<MultiSelectOption[]>(() => {
    const groupName = new Map((groups.data ?? []).map((g) => [g.id, g.name]))
    return candidates.map((c) => ({
      id: c.id,
      label: c.name,
      group: groupName.get(c.category_group_id) ?? 'Ungrouped',
    }))
  }, [candidates, groups.data])

  const targetByCategory = useMemo(
    () => new Map((targets.data ?? []).map((t) => [t.category_id, t])),
    [targets.data]
  )

  function close() {
    setOpen(false)
    setPicked([])
  }

  function importPicked() {
    const chosen = new Set(picked)
    const items: DraftItem[] = candidates
      .filter((c) => chosen.has(c.id))
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
    close()
  }

  if (!open) {
    return (
      <div className="planner__panel-toggle">
        <button type="button" className="guide-link-button" onClick={() => setOpen(true)}>
          Pull in budget categories
        </button>
      </div>
    )
  }

  const loading = categories.isLoading || groups.isLoading
  const empty = !loading && candidates.length === 0

  const footer =
    loading || empty ? (
      <div className="planner__import-footer">
        <button type="button" className="guide-link-button" onClick={close}>
          Close
        </button>
      </div>
    ) : (
      <div className="planner__import-footer">
        <label className="planner__import-destination">
          <span>Add under</span>
          <select
            aria-label="Which paycheck the rows go under"
            value={destination}
            onChange={(e) => setDestination(Number(e.target.value))}
          >
            {Array.from({ length: props.paycheckCount }, (_, i) => (
              <option key={i} value={i}>
                Paycheck {i + 1}
              </option>
            ))}
          </select>
        </label>
        <div className="planner__import-confirm">
          <button type="button" className="guide-link-button" onClick={close}>
            Cancel
          </button>
          <button
            type="button"
            className="guide-checkup__run"
            disabled={picked.length === 0}
            onClick={importPicked}
          >
            <Plus size={12} aria-hidden /> Add {picked.length || ''}{' '}
            {picked.length === 1 ? 'category' : 'categories'}
          </button>
        </div>
      </div>
    )

  return (
    <>
      <div className="planner__panel-toggle">
        <button type="button" className="guide-link-button" onClick={() => setOpen(true)}>
          Pull in budget categories
        </button>
      </div>
      <Dialog
        title="Pull in budget categories"
        onClose={close}
        historyKey="planner-import"
        width="md"
        footer={footer}
      >
        {loading ? (
          <p className="tool__hint">Loading categories…</p>
        ) : empty ? (
          <p className="tool__hint">
            Every category the budget offers is already in this plan — or the budget has none yet.
          </p>
        ) : (
          <>
            <p className="tool__hint planner__import-hint">
              Amounts start from each category’s monthly target where it has one; everything else
              starts blank.
            </p>
            <GroupedMultiSelect
              options={options}
              selectedIds={picked}
              onChange={setPicked}
              onEscape={close}
              searchPlaceholder="Search categories…"
              emptyText="No category by that name"
              className="planner__import-picker"
            />
          </>
        )}
      </Dialog>
    </>
  )
}
