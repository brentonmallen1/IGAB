import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Wallet, Plus, BarChart2, Menu } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import { useUpdateStatus } from '../../../api/system'
import { useAIBadgeState } from '../../ai/useAIBadgeState'
import './BottomNav.css'

function navItemClass({ isActive }: { isActive: boolean }) {
  return `bottom-nav__item ${isActive ? 'bottom-nav__item--active' : ''}`
}

/** Mobile-only primary navigation (hidden above 768px). */
export function BottomNav() {
  const openQuickAdd = useUIStore((s) => s.openQuickAdd)
  const openMoreSheet = useUIStore((s) => s.openMoreSheet)
  // Everything badged lives INSIDE the sheet, where it is invisible until you
  // open it — which is no notification at all. The button carries a dot when
  // anything behind it is asking for attention. (The System entry's update dot
  // had this problem already; it is the same rollup.)
  const aiBadge = useAIBadgeState()
  const updateAvailable = useUpdateStatus().data?.update_available === true
  const somethingInside = aiBadge.kind !== 'none' || updateAvailable

  return (
    <nav className="bottom-nav" aria-label="Primary">
      <NavLink to="/budget" className={navItemClass}>
        <LayoutDashboard size={20} />
        <span>Budget</span>
      </NavLink>
      <NavLink to="/accounts" className={navItemClass}>
        <Wallet size={20} />
        <span>Accounts</span>
      </NavLink>
      <div className="bottom-nav__add-slot">
        <button
          className="bottom-nav__add press-scale"
          onClick={openQuickAdd}
          aria-label="Add transaction"
        >
          <Plus size={24} />
        </button>
      </div>
      <NavLink to="/reports" className={navItemClass}>
        <BarChart2 size={20} />
        <span>Reports</span>
      </NavLink>
      <button className="bottom-nav__item" onClick={openMoreSheet}>
        <span className="bottom-nav__icon-wrap">
          <Menu size={20} />
          {somethingInside && (
            <span
              className="count-badge count-badge--dot count-badge--accent bottom-nav__rollup"
              title="Something inside needs attention"
            >
              <span className="sr-only">Something inside needs attention</span>
            </span>
          )}
        </span>
        <span>More</span>
      </button>
    </nav>
  )
}
