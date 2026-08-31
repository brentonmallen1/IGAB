import { useEffect, useRef, useState } from 'react'
import {
  AlignJustify,
  AlignLeft,
  ArrowUpDown,
  ChevronDown,
  Layers,
  ListFilter,
  Plus,
  Search,
  Settings2,
  X,
} from 'lucide-react'
import { useBudgetFilters } from '../../../api/budgetFilters'
import { useBudgetViews } from '../../../api/budgetViews'
import { useUIStore, QUICK_FILTER_LABELS, QUICK_FILTER_VARIANTS } from '../../../stores/uiStore'
import { ContextMenu } from '../../common/ContextMenu/ContextMenu'
import type { CategoryBalance } from '../../../types'
import { reorderBlock } from '../reorderAvailability'
import './BudgetFilterBar.css'

interface Props {
  budgetId: string
  categoryBalances: CategoryBalance[]
}

//: Shown once, to whoever had saved views before the rename. Renaming someone's
//: saved things without a word reads as data loss, however much better the new
//: name is. Keyed in localStorage so it is genuinely once, not once per reload.
const RENAME_NOTICE_KEY = 'igab-filters-rename-seen'
//: Anything created before the rename migration belongs to a user who had
//: "views"; anything after was always called a filter. A date beats a flag
//: column for a notice that should disappear in a release or two.
const RENAME_SHIPPED_AT = '2026-08-21'

export function BudgetFilterBar({ budgetId, categoryBalances }: Props) {
  const { data: filters } = useBudgetFilters(budgetId)
  const { data: views } = useBudgetViews(budgetId)
  const activeViewId = useUIStore((s) => s.activeViewId)
  const setActiveView = useUIStore((s) => s.setActiveView)
  const openModal = useUIStore((s) => s.openModal)
  const viaPointer = useRef(false)
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
  const toggleBudgetRowMode = useUIStore((s) => s.toggleBudgetRowMode)
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
  // — the same function Fill Underfunded asks — so a chip's count always
  // matches what the rows show and what the button will do.
  const counts = {
    overspent: categoryBalances.filter((b) => (b.available ?? 0) < 0).length,
    underfunded: categoryBalances.filter((b) => b.target_status === 'underfunded').length,
    'money-available': categoryBalances.filter((b) => (b.available ?? 0) > 0).length,
    overfunded: categoryBalances.filter((b) => b.target_status === 'overfunded').length,
  }

  function handleMenuSelect(id: string) {
    if (id === 'new') openModal('filter')
    else if (id === 'manage') openModal('manage-filters')
    else if (id === 'new-view') openModal('view')
    else if (id === 'manage-views') openModal('manage-views')
  }

  function handleAllClick() {
    setActiveFilter(null)
    setActiveQuickFilter(null)
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

  const isAllActive = activeFilterId === null && activeQuickFilter === null

  return (
    <div className="budget-filter-bar surface surface--chrome">
      {/* How categories are grouped. Separate control from the filter chips
          because it is a separate question — a view decides the arrangement,
          a filter decides which of those categories show. Both can be on. */}
      {(views?.length ?? 0) > 0 && (
        <>
          <span className={`budget-filter-bar__view ${activeViewId ? 'active' : ''}`}>
            <Layers size={12} className="budget-filter-bar__view-icon" />
            <span className="budget-filter-bar__view-label">
              {views!.find((v) => v.id === activeViewId)?.name ?? 'Default groups'}
            </span>
            <ChevronDown size={12} className="budget-filter-bar__view-caret" />
            {/* The real control, stretched invisibly over the whole chip. The
                icon, label and caret above are only its appearance — as
                siblings they were unclickable, leaving the chip's padding and
                both icons dead to the pointer. */}
            <select
              className="budget-filter-bar__view-select"
              value={activeViewId ?? ''}
              onPointerDown={() => {
                viaPointer.current = true
              }}
              onKeyDown={() => {
                viaPointer.current = false
              }}
              onChange={(e) => {
                setActiveView(e.target.value || null)
                // A select keeps focus after a click, and browsers count that
                // as focus-visible, so the ring lingered after the user was
                // plainly finished. Only drop focus for pointer use — keyboard
                // users change the value with arrow keys and must keep it.
                if (viaPointer.current) e.currentTarget.blur()
              }}
              title="How categories are grouped"
              aria-label="Category view"
            >
              <option value="">Default groups</option>
              {views!.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </span>
          {/* The grouping control answers a different question from the chips
              beside it, so a rule keeps them from reading as one row of peers. */}
          <span className="budget-filter-bar__divider" aria-hidden="true" />
        </>
      )}

      <button
        className={`budget-filter-bar__btn ${isAllActive ? 'active' : ''}`}
        onClick={handleAllClick}
      >
        All
      </button>

      {quickFilterOrder.map((filter) => {
        const count = counts[filter]
        if (count === 0) return null
        const variant = QUICK_FILTER_VARIANTS[filter]
        const label =
          filter === 'overspent'
            ? `${count} Overspent`
            : filter === 'underfunded'
              ? `${count} Underfunded`
              : QUICK_FILTER_LABELS[filter]
        return (
          <button
            key={filter}
            className={`budget-filter-bar__btn budget-filter-bar__btn--${variant} ${activeQuickFilter === filter ? 'active' : ''}`}
            onClick={() => setActiveQuickFilter(activeQuickFilter === filter ? null : filter)}
          >
            {label}
          </button>
        )
      })}

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

      {filters?.map((saved) => (
        <button
          key={saved.id}
          className={`budget-filter-bar__btn ${activeFilterId === saved.id ? 'active' : ''}`}
          onClick={() => setActiveFilter(saved.id)}
          onDoubleClick={() => openModal('filter', saved.id)}
          title="Double-click to edit"
        >
          {saved.name}
        </button>
      ))}

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
        <button
          className="budget-filter-bar__menu-btn"
          onClick={toggleBudgetRowMode}
          title={
            budgetRowMode === 'expanded' ? 'Switch to compact rows' : 'Switch to expanded rows'
          }
          aria-label="Compact rows"
          aria-pressed={budgetRowMode !== 'expanded'}
        >
          {budgetRowMode === 'expanded' ? <AlignLeft size={14} /> : <AlignJustify size={14} />}
        </button>
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
        {menuOpen &&
          menuAnchorRef.current &&
          (() => {
            const rect = menuAnchorRef.current.getBoundingClientRect()
            return (
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
                position={{ x: rect.right, y: rect.bottom + 4, alignRight: true }}
              />
            )
          })()}
      </div>
    </div>
  )
}
