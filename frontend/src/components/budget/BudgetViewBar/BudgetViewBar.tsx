import { useEffect, useRef, useState } from 'react'
import { ListFilter, Plus, Search, Settings2, AlignJustify, AlignLeft, X } from 'lucide-react'
import { useBudgetViews } from '../../../api/budgetViews'
import { useUIStore } from '../../../stores/uiStore'
import { targetStatus } from '../../../utils/targets'
import { ContextMenu } from '../../common/ContextMenu/ContextMenu'
import type { CategoryBalance, CategoryTarget } from '../../../types'
import './BudgetViewBar.css'

interface Props {
  budgetId: string
  categoryBalances: CategoryBalance[]
  targets: CategoryTarget[]
}

export function BudgetViewBar({ budgetId, categoryBalances, targets }: Props) {
  const { data: views } = useBudgetViews(budgetId)
  const activeBudgetViewId = useUIStore((s) => s.activeBudgetViewId)
  const activeQuickFilter = useUIStore((s) => s.activeQuickFilter)
  const quickFilterOrder = useUIStore((s) => s.quickFilterOrder)
  const setActiveBudgetView = useUIStore((s) => s.setActiveBudgetView)
  const setActiveQuickFilter = useUIStore((s) => s.setActiveQuickFilter)
  const openViewModal = useUIStore((s) => s.openViewModal)
  const openManageViewsModal = useUIStore((s) => s.openManageViewsModal)
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

  const targetMap = new Map(targets.map((t) => [t.category_id, t]))

  // Funding status via utils/targets — the same rules as the row pill and
  // Fill Underfunded, so a chip's count always matches what the rows show.
  const counts = {
    overspent: categoryBalances.filter((b) => b.available < 0).length,
    underfunded: categoryBalances.filter((b) => {
      const t = targetMap.get(b.category_id)
      return t != null && targetStatus(t, b.assigned, b.available) === 'underfunded'
    }).length,
    'money-available': categoryBalances.filter((b) => b.available > 0).length,
    overfunded: categoryBalances.filter((b) => {
      const t = targetMap.get(b.category_id)
      return t != null && targetStatus(t, b.assigned, b.available) === 'overfunded'
    }).length,
  }

  const FILTER_LABELS: Record<string, string> = {
    overspent: 'Overspent',
    underfunded: 'Underfunded',
    'money-available': 'Money Available',
    overfunded: 'Overfunded',
  }
  const FILTER_VARIANTS: Record<string, string> = {
    overspent: 'negative',
    underfunded: 'warning',
    'money-available': 'positive',
    overfunded: 'positive',
  }

  function handleMenuSelect(id: string) {
    if (id === 'new') openViewModal()
    else if (id === 'manage') openManageViewsModal()
  }

  function handleAllClick() {
    setActiveBudgetView(null)
    setActiveQuickFilter(null)
  }

  const isAllActive = activeBudgetViewId === null && activeQuickFilter === null

  return (
    <div className="budget-view-bar">
      <button
        className={`budget-view-bar__btn ${isAllActive ? 'active' : ''}`}
        onClick={handleAllClick}
      >
        All
      </button>

      {quickFilterOrder.map((filter) => {
        const count = counts[filter]
        if (count === 0) return null
        const variant = FILTER_VARIANTS[filter]
        const label = filter === 'overspent'
          ? `${count} Overspent`
          : filter === 'underfunded'
          ? `${count} Underfunded`
          : FILTER_LABELS[filter]
        return (
          <button
            key={filter}
            className={`budget-view-bar__btn budget-view-bar__btn--${variant} ${activeQuickFilter === filter ? 'active' : ''}`}
            onClick={() => setActiveQuickFilter(activeQuickFilter === filter ? null : filter)}
          >
            {label}
          </button>
        )
      })}

      {views?.map((view) => (
        <button
          key={view.id}
          className={`budget-view-bar__btn ${activeBudgetViewId === view.id ? 'active' : ''}`}
          onClick={() => setActiveBudgetView(view.id)}
          onDoubleClick={() => openViewModal(view.id)}
          title="Double-click to edit"
        >
          {view.name}
        </button>
      ))}

      <div className={`budget-view-bar__search ${categorySearch ? 'has-value' : ''}`}>
        <Search size={13} className="budget-view-bar__search-icon" />
        <input
          ref={searchRef}
          className="budget-view-bar__search-input"
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
            className="budget-view-bar__search-clear"
            onClick={() => setCategorySearch('')}
            title="Clear filter"
          >
            <X size={12} />
          </button>
        )}
      </div>

      <div className="budget-view-bar__menu-wrap">
        <button
          className="budget-view-bar__menu-btn"
          onClick={toggleBudgetRowMode}
          title={budgetRowMode === 'expanded' ? 'Switch to compact rows' : 'Switch to expanded rows'}
        >
          {budgetRowMode === 'expanded' ? <AlignLeft size={14} /> : <AlignJustify size={14} />}
        </button>
        <button
          ref={menuAnchorRef}
          className="budget-view-bar__menu-btn"
          onClick={() => setMenuOpen((v) => !v)}
          title="View options"
        >
          <ListFilter size={14} />
        </button>
        {menuOpen && menuAnchorRef.current && (() => {
          const rect = menuAnchorRef.current.getBoundingClientRect()
          return (
            <ContextMenu
              items={[
                { id: 'new', label: 'New View', icon: Plus },
                { id: 'manage', label: 'Manage Views', icon: Settings2 },
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
