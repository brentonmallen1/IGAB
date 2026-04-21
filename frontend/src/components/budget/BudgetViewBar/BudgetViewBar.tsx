import { useRef, useState } from 'react'
import { ListFilter, Plus, Settings2, AlignJustify, AlignLeft } from 'lucide-react'
import { useBudgetViews } from '../../../api/budgetViews'
import { useUIStore } from '../../../stores/uiStore'
import { ContextMenu } from '../../common/ContextMenu/ContextMenu'
import './BudgetViewBar.css'

interface Props {
  budgetId: string
}

export function BudgetViewBar({ budgetId }: Props) {
  const { data: views } = useBudgetViews(budgetId)
  const activeBudgetViewId = useUIStore((s) => s.activeBudgetViewId)
  const setActiveBudgetView = useUIStore((s) => s.setActiveBudgetView)
  const openViewModal = useUIStore((s) => s.openViewModal)
  const budgetRowMode = useUIStore((s) => s.budgetRowMode)
  const toggleBudgetRowMode = useUIStore((s) => s.toggleBudgetRowMode)

  const [menuOpen, setMenuOpen] = useState(false)
  const menuAnchorRef = useRef<HTMLButtonElement>(null)

  function handleMenuSelect(id: string) {
    if (id === 'new') openViewModal()
    else if (id === 'manage' && views && views.length > 0) openViewModal(views[0].id)
  }

  return (
    <div className="budget-view-bar">
      <button
        className={`budget-view-bar__btn ${activeBudgetViewId === null ? 'active' : ''}`}
        onClick={() => setActiveBudgetView(null)}
      >
        All
      </button>

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
              { id: 'manage', label: 'Manage Views', icon: Settings2, disabled: !views?.length },
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
