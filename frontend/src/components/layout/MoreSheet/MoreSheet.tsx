import { useNavigate } from 'react-router-dom'
import { Users, CalendarClock, Upload, Settings, ChevronLeft, LogOut, Palette, Landmark, Sparkles, Eye, EyeOff } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { THEMES } from '../../../stores/appStore'
import { useAIStatus } from '../../../api/ai'
import { useUpdateStatus } from '../../../api/system'
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
  const privacyMode = useAppStore((s) => s.privacyMode)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)
  const navigate = useNavigate()
  const logout = useLogout()
  const aiAvailable = useAIStatus().data?.available === true
  const updateAvailable = useUpdateStatus().data?.update_available === true

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
        <button className="more-sheet__item" onClick={() => go('/liabilities')}>
          <Landmark size={18} />
          <span>Liabilities</span>
        </button>
        {aiAvailable && (
          <button className="more-sheet__item" onClick={() => go('/ai-activity')}>
            <Sparkles size={18} />
            <span>AI Activity</span>
          </button>
        )}
        <button className="more-sheet__item" onClick={() => go('/import')}>
          <Upload size={18} />
          <span>Import</span>
        </button>
        <button className="more-sheet__item" onClick={() => go('/settings')}>
          <Settings size={18} />
          <span>Settings</span>
          {updateAvailable && (
            <span
              className="more-sheet__update-badge"
              title="Update available — see Settings → Updates"
            />
          )}
        </button>
        <button className="more-sheet__item" onClick={togglePrivacyMode} aria-pressed={privacyMode}>
          {privacyMode ? <EyeOff size={18} /> : <Eye size={18} />}
          <span>{privacyMode ? 'Show amounts' : 'Hide amounts'}</span>
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
