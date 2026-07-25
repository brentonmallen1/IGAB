import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Wallet, Plus, BarChart2, Menu } from 'lucide-react'
import { useUIStore } from '../../../stores/uiStore'
import './BottomNav.css'

function navItemClass({ isActive }: { isActive: boolean }) {
  return `bottom-nav__item ${isActive ? 'bottom-nav__item--active' : ''}`
}

/** Mobile-only primary navigation (hidden above 768px). */
export function BottomNav() {
  const openQuickAdd = useUIStore((s) => s.openQuickAdd)
  const openMoreSheet = useUIStore((s) => s.openMoreSheet)

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
        <button className="bottom-nav__add" onClick={openQuickAdd} aria-label="Add transaction">
          <Plus size={24} />
        </button>
      </div>
      <NavLink to="/reports" className={navItemClass}>
        <BarChart2 size={20} />
        <span>Reports</span>
      </NavLink>
      <button className="bottom-nav__item" onClick={openMoreSheet}>
        <Menu size={20} />
        <span>More</span>
      </button>
    </nav>
  )
}
