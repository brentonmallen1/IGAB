import { ChevronLeft, ChevronRight, Menu } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { formatMonth, addMonths } from '../../../utils/dates'
import './Header.css'

export function Header() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const setMobileSidebarOpen = useUIStore((s) => s.setMobileSidebarOpen)

  return (
    <header className="header">
      <button
        className="header__menu-btn"
        onClick={() => setMobileSidebarOpen(true)}
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>
      <div className="header__month-nav">
        <button
          className="header__month-btn"
          onClick={() => setSelectedMonth(addMonths(selectedMonth, -1))}
          aria-label="Previous month"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="header__month-label">{formatMonth(selectedMonth)}</span>
        <button
          className="header__month-btn"
          onClick={() => setSelectedMonth(addMonths(selectedMonth, 1))}
          aria-label="Next month"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </header>
  )
}
