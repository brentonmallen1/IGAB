import { useEffect, useRef, useState } from 'react'
import { ArrowUpDown, Funnel, Layers, ListFilter, Plus, Search, Settings2, X } from 'lucide-react'
import { useBudgetFilters } from '../../../api/budgetFilters'
import { useBudgetViews } from '../../../api/budgetViews'
import { useUIStore, BUDGET_ROW_MODES } from '../../../stores/uiStore'
import { ContextMenu } from '../../common/ContextMenu/ContextMenu'
import { SelectChip } from '../../common/SelectChip/SelectChip'
import type { CategoryBalance } from '../../../types'
import { reorderBlock } from '../reorderAvailability'
import './BudgetFilterBar.css'
import { filterMenu, parseChoice } from '../budgetFilterMenu'

interface Props {
  budgetId: string
  categoryBalances: CategoryBalance[]
  /** The grid measures this bar to offset the column header below it — the
   *  two are stacked sticky rows and this one wraps. See useMeasuredHeight. */
  barRef?: (node: HTMLDivElement | null) => void
}

//: Shown once, to whoever had saved views before the rename. Renaming someone's
//: saved things without a word reads as data loss, however much better the new
//: name is. Keyed in localStorage so it is genuinely once, not once per reload.
const RENAME_NOTICE_KEY = 'igab-filters-rename-seen'
//: Anything created before the rename migration belongs to a user who had
//: "views"; anything after was always called a filter. A date beats a flag
//: column for a notice that should disappear in a release or two.
const RENAME_SHIPPED_AT = '2026-08-21'

export function BudgetFilterBar({ budgetId, categoryBalances, barRef }: Props) {
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: views } = useBudgetViews(budgetId)
  const activeViewId = useUIStore((s) => s.activeViewId)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const openModal = useUIStore((s) => s.openModal)
  const [renameNoticeSeen, setRenameNoticeSeen] = useState(
    () => localStorage.getItem(RENAME_NOTICE_KEY) === '1'
  )
  // Only for filters that predate the rename. Keying off "has any filter"
  // showed a brand-new install "your saved views are now called filters" the
  // first time it created one, describing a migration it never lived through.
  const hasPreRenameFilter = (filters ?? []).some(
    (f) => f.created_at != null && f.created_at < RENAME_SHIPPED_AT
  )
  const showRenameNotice = !renameNoticeSeen && hasPreRenameFilter
  const dismissRenameNotice = () => {
    localStorage.setItem(RENAME_NOTICE_KEY, '1')
    setRenameNoticeSeen(true)
  }
  const activeFilterId = useUIStore((s) => s.activeFilterId)
  const activeQuickFilter = useUIStore((s) => s.activeQuickFilter)
  const quickFilterOrder = useUIStore((s) => s.quickFilterOrder)
  const setActiveFilter = useUIStore((s) => s.setActiveFilter)
  const setActiveQuickFilter = useUIStore((s) => s.setActiveQuickFilter)
  const budgetRowMode = useUIStore((s) => s.budgetRowMode)
  const setBudgetRowMode = useUIStore((s) => s.setBudgetRowMode)
  const categorySearch = useUIStore((s) => s.categorySearch)
  const setCategorySearch = useUIStore((s) => s.setCategorySearch)

  const [menuOpen, setMenuOpen] = useState(false)
  const menuAnchorRef = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  // The filter is ephemeral — leaving the budget page clears it so the user
  // never comes back to a mysteriously short category list
  useEffect(() => () => useUIStore.getState().setCategorySearch(''), [])

  // The persisted selections are not budget-scoped, so after switching budgets
  // (or a delete from another tab) they can point at a view or filter this
  // budget doesn't have. Self-heal to the default rather than letting a stale
  // id ride along into report queries.
  useEffect(() => {
    if (views && activeViewId && !views.some((v) => v.id === activeViewId)) setActiveView(null)
  }, [views, activeViewId, setActiveView])
  useEffect(() => {
    if (filters && activeFilterId && !filters.some((f) => f.id === activeFilterId)) {
      setActiveFilter(null)
    }
  }, [filters, activeFilterId, setActiveFilter])

  // Funding status comes from the row, computed by the server's TargetService
  // — the same function Fill Underfunded asks — so a count always matches what
  // the rows show and what the button will do.
  const counts = {
    overspent: categoryBalances.filter((b) => (b.available ?? 0) < 0).length,
    underfunded: categoryBalances.filter((b) => b.target_status === 'underfunded').length,
    pending: categoryBalances.filter((b) => b.target_status === 'pending').length,
    'money-available': categoryBalances.filter((b) => (b.available ?? 0) > 0).length,
    overfunded: categoryBalances.filter((b) => b.target_status === 'overfunded').length,
  }

  function handleMenuSelect(id: string) {
    if (id === 'new') openModal('filter')
    else if (id === 'manage') openModal('manage-filters')
    else if (id === 'new-view') openModal('view')
    else if (id === 'manage-views') openModal('manage-views')
  }

  // Why the drag handles are gone, from the module the grid gates on — so the
  // bar cannot name a reason the grid is not actually using. Nothing is shown
  // when reordering is available, which is the ordinary case.
  //
  // `viewActive` is the RESOLVED view, not the stored id, because that is what
  // the grid gates on. While the view list is still loading — or while a
  // persisted id points at a view this budget doesn't have, before the
  // self-heal above runs — the id is set and the view is not, and the two
  // surfaces would tell different stories about the same handles.
  const blocked = reorderBlock({
    savedFilterActive: activeFilterId != null,
    quickFilterActive: activeQuickFilter != null,
    search: categorySearch,
    viewActive: views?.some((v) => v.id === activeViewId) ?? false,
  })

  // One control for a choice that was always one choice: the store clears
  // either selection when the other is set, so the row of buttons this
  // replaces could never have two of them on. `budgetFilterMenu` says what it
  // offers; editing a saved filter moved to Manage Filters, which is where
  // someone looks for it rather than double-clicking a chip that no longer
  // exists.
  const menu = filterMenu({
    quickFilterOrder,
    counts,
    saved: filters ?? [],
    activeQuickFilter,
    activeFilterId,
  })

  function handleFilterChange(value: string) {
    const choice = parseChoice(value)
    if (choice.kind === 'quick') setActiveQuickFilter(choice.filter)
    else if (choice.kind === 'saved') setActiveFilter(choice.id)
    else {
      setActiveFilter(null)
      setActiveQuickFilter(null)
    }
  }

  return (
    <div className="budget-filter-bar surface surface--chrome" ref={barRef}>
      {/* How categories are grouped. Separate control from the filter beside
          it because it is a separate question — a view decides the
          arrangement, a filter decides which of those categories show. Both
          can be on. */}
      {(views?.length ?? 0) > 0 && (
        <>
          <SelectChip
            value={activeViewId ?? ''}
            onChange={(v) => setActiveView(v || null)}
            groups={[{ label: '', options: views!.map((v) => ({ value: v.id, label: v.name })) }]}
            placeholder="Default groups"
            icon={Layers}
            active={activeViewId != null}
            title="How categories are grouped"
            ariaLabel="Category view"
          />
          {/* The grouping control answers a different question from the filter
              beside it, so a rule keeps them from reading as peers. */}
          <span className="budget-filter-bar__divider" aria-hidden="true" />
        </>
      )}

      <SelectChip
        value={menu.value}
        onChange={handleFilterChange}
        groups={menu.groups}
        placeholder="All categories"
        icon={Funnel}
        active={menu.value !== ''}
        title={
          menu.attention > 0
            ? `${menu.attention} ${menu.attention === 1 ? 'category is' : 'categories are'} overspent`
            : 'Which categories the grid shows'
        }
        ariaLabel="Filter categories"
      >
        {/* The one thing collapsing the row would otherwise stop saying out
            loud. A fixed-size dot rather than a count, so the bar's width
            still does not move with the budget's state. */}
        {menu.attention > 0 && (
          <span className="budget-filter-bar__attention">
            <span className="sr-only">
              {menu.attention} overspent {menu.attention === 1 ? 'category' : 'categories'}
            </span>
          </span>
        )}
      </SelectChip>

      {blocked && (
        <span className="budget-filter-bar__reorder-note" role="status" title={blocked.detail}>
          <ArrowUpDown size={12} aria-hidden="true" />
          <span className="budget-filter-bar__reorder-note-text">{blocked.short}</span>
          <span className="sr-only">. {blocked.detail}</span>
        </span>
      )}

      {showRenameNotice && (
        <span className="budget-filter-bar__notice" role="status">
          Your saved <strong>views</strong> are now called <strong>filters</strong> — same saved
          category sets, clearer name. Nothing was lost.
          <button
            type="button"
            className="budget-filter-bar__notice-close"
            onClick={dismissRenameNotice}
            aria-label="Dismiss"
          >
            <X size={12} />
          </button>
        </span>
      )}

      <div className={`budget-filter-bar__search ${categorySearch ? 'has-value' : ''}`}>
        <Search size={13} className="budget-filter-bar__search-icon" />
        <input
          ref={searchRef}
          className="budget-filter-bar__search-input"
          type="text"
          value={categorySearch}
          onChange={(e) => setCategorySearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setCategorySearch('')
              searchRef.current?.blur()
            }
          }}
          placeholder="Filter categories…"
          aria-label="Filter categories by name"
        />
        {categorySearch && (
          <button
            className="budget-filter-bar__search-clear"
            onClick={() => setCategorySearch('')}
            title="Clear filter"
          >
            <X size={12} />
          </button>
        )}
      </div>

      <div className="budget-filter-bar__menu-wrap">
        <div className="budget-filter-bar__density" role="group" aria-label="Row density">
          {BUDGET_ROW_MODES.map((mode) => (
            <button
              key={mode.value}
              type="button"
              className={`budget-filter-bar__density-btn ${budgetRowMode === mode.value ? 'active' : ''}`}
              onClick={() => setBudgetRowMode(mode.value)}
              aria-pressed={budgetRowMode === mode.value}
              title={mode.hint}
            >
              {mode.label}
            </button>
          ))}
        </div>
        <button
          ref={menuAnchorRef}
          className="budget-filter-bar__menu-btn"
          onClick={() => setMenuOpen((v) => !v)}
          title="Filters and views"
          aria-label="Filters and views"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
        >
          <ListFilter size={14} />
        </button>
        {menuOpen && (
          <ContextMenu
            items={[
              { id: 'new', label: 'New Filter', icon: Plus },
              { id: 'manage', label: 'Manage Filters', icon: Settings2 },
              // Views are a different axis from filters, so they sit below a
              // rule rather than reading as two more filter actions.
              { id: 'sep', label: '', separator: true },
              { id: 'new-view', label: 'New View', icon: Layers },
              { id: 'manage-views', label: 'Manage Views', icon: Settings2 },
            ]}
            onSelect={handleMenuSelect}
            onClose={() => setMenuOpen(false)}
            anchor={menuAnchorRef}
            alignRight
          />
        )}
      </div>
    </div>
  )
}
