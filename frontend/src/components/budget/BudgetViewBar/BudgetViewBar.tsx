import { useRef, useState } from 'react'
import { ListFilter, Plus, Settings2, AlignJustify, AlignLeft } from 'lucide-react'
import { useBudgetViews } from '../../../api/budgetViews'
import { useUIStore } from '../../../stores/uiStore'
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

  const [menuOpen, setMenuOpen] = useState(false)
  const menuAnchorRef = useRef<HTMLButtonElement>(null)

  const targetMap = new Map(targets.map((t) => [t.category_id, t]))

  const counts = {
    overspent: categoryBalances.filter((b) => b.available < 0).length,
    underfunded: categoryBalances.filter((b) => {
      const t = targetMap.get(b.category_id)
      return t != null && b.assigned < t.target_amount
    }).length,
    'money-available': categoryBalances.filter((b) => b.available > 0).length,
    overfunded: categoryBalances.filter((b) => {
      const t = targetMap.get(b.category_id)
      return t != null && b.assigned > t.target_amount
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
        {menuOpen && (
          <ContextMenu
            items={[
              { id: 'new', label: 'New View', icon: Plus },
              { id: 'manage', label: 'Manage Views', icon: Settings2 },
            ]}
            onSelect={handleMenuSelect}
            onClose={() => setMenuOpen(false)}
            className="budget-view-bar__dropdown"
          />
        )}
      </div>
    </div>
  )
}
