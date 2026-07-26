import { useNavigate } from 'react-router-dom'
import { Users, CalendarClock, Upload, Settings, ChevronLeft, LogOut, Palette, Landmark } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { THEMES } from '../Header/Header'
import { useLogout } from '../../../api/auth'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import './MoreSheet.css'

/** Everything that doesn't earn a bottom-nav tab: secondary pages, budget switch, theme, sign out. */
export function MoreSheet() {
  const open = useUIStore((s) => s.moreSheetOpen)
  const closeMoreSheet = useUIStore((s) => s.closeMoreSheet)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const navigate = useNavigate()
  const logout = useLogout()

  function go(path: string) {
    closeMoreSheet()
    navigate(path)
  }

  return (
    <BottomSheet open={open} onClose={closeMoreSheet} historyKey="more">
      <div className="more-sheet">
        <button className="more-sheet__item" onClick={() => go('/payees')}>
          <Users size={18} />
          <span>Payees</span>
        </button>
        <button className="more-sheet__item" onClick={() => go('/scheduled')}>
          <CalendarClock size={18} />
          <span>Scheduled</span>
        </button>
        <button className="more-sheet__item" onClick={() => go('/debts')}>
          <Landmark size={18} />
          <span>Debts</span>
        </button>
        <button className="more-sheet__item" onClick={() => go('/import')}>
          <Upload size={18} />
          <span>Import</span>
        </button>
        <button className="more-sheet__item" onClick={() => go('/settings')}>
          <Settings size={18} />
          <span>Settings</span>
        </button>
        <button
          className="more-sheet__item"
          onClick={() => {
            closeMoreSheet()
            clearCurrentBudget()
            navigate('/budgets')
          }}
        >
          <ChevronLeft size={18} />
          <span>Switch budget</span>
        </button>
        <button className="more-sheet__item" onClick={logout}>
          <LogOut size={18} />
          <span>Sign out</span>
        </button>

        <div className="more-sheet__section-label">
          <Palette size={14} />
          <span>Theme</span>
        </div>
        <div className="more-sheet__themes">
          {THEMES.map((t) => (
            <button
              key={t.value}
              className={`more-sheet__theme ${theme === t.value ? 'more-sheet__theme--active' : ''}`}
              onClick={() => setTheme(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
    </BottomSheet>
  )
}
