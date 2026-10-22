import { useBudgetFilters } from '../../api/budgetFilters'
import { useBudgetViews } from '../../api/budgetViews'
import { QUICK_FILTER_LABELS, useUIStore, type QuickFilter } from '../../stores/uiStore'

/**
 * What is narrowing the budget grid right now, as things a person can see and
 * undo one by one: a status, a saved filter, a search, a view.
 *
 * On a phone the controls that set these live behind the Tools sheet, so the
 * grid itself has to say when it is not showing everything — a filtered list
 * that reads like a short budget is the one thing it must never do. Two
 * places ask (the strip above the grid, the dot on the Tools button), so the
 * answer is here once.
 */

export type NarrowingKey = 'status' | 'filter' | 'search' | 'view'

export interface NarrowingPart {
  key: NarrowingKey
  label: string
}

/** Pure: names in, the parts to show out, in the order they narrow. */
export function gridNarrowing({
  status,
  savedFilter,
  search,
  view,
}: {
  status: QuickFilter | null
  /** The saved filter's name, or null — resolved, not the stored id. */
  savedFilter: string | null
  search: string
  /** The view's name, or null — resolved, not the stored id. */
  view: string | null
}): NarrowingPart[] {
  const parts: NarrowingPart[] = []
  if (status) parts.push({ key: 'status', label: QUICK_FILTER_LABELS[status] })
  if (savedFilter) parts.push({ key: 'filter', label: savedFilter })
  const q = search.trim()
  if (q) parts.push({ key: 'search', label: `“${q}”` })
  if (view) parts.push({ key: 'view', label: `View: ${view}` })
  return parts
}

/** The wiring: the store's selections resolved against this budget's saved
 *  filters and views, plus how to undo each. A stored id that names nothing
 *  here (another budget's, or one deleted elsewhere) narrows nothing — the
 *  same reading the grid and the filter bar's self-heal take. */
export function useGridNarrowing(budgetId: string) {
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: views } = useBudgetViews(budgetId)
  const status = useUIStore((s) => s.activeQuickFilter)
  const filterId = useUIStore((s) => s.activeFilterId)
  const viewId = useUIStore((s) => s.activeViewId)
  const search = useUIStore((s) => s.categorySearch)
  const setActiveQuickFilter = useUIStore((s) => s.setActiveQuickFilter)
  const setActiveFilter = useUIStore((s) => s.setActiveFilter)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const setCategorySearch = useUIStore((s) => s.setCategorySearch)

  const parts = gridNarrowing({
    status,
    savedFilter: filters?.find((f) => f.id === filterId)?.name ?? null,
    search,
    view: views?.find((v) => v.id === viewId)?.name ?? null,
  })

  function clear(key: NarrowingKey) {
    if (key === 'status') setActiveQuickFilter(null)
    else if (key === 'filter') setActiveFilter(null)
    else if (key === 'search') setCategorySearch('')
    else setActiveView(null)
  }

  return { parts, clear }
}
