import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { UserCircle2, Users, CalendarClock, Upload, Settings, ChevronDown, ChevronLeft, LogOut, Moon, Palette, Landmark, Compass, Sparkles, Sun, Eye, EyeOff } from 'lucide-react'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { PALETTES, getPaletteForTheme, isLightTheme } from '../../../stores/appStore'
import { useUpdateStatus } from '../../../api/system'
import { useCurrentUser, useLogout } from '../../../api/auth'
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

  // Every theme is a palette family with a dark and a light look, so the
  // picker decomposes the same way: one mode toggle, one dropdown of styles.
  const palette = getPaletteForTheme(theme)
  const singleLook = palette.dark === palette.light
  const [mode, setMode] = useState<'dark' | 'light'>(() =>
    !singleLook && isLightTheme(theme) ? 'light' : 'dark'
  )
  // Theme can change elsewhere (Settings, command palette) — follow it, but
  // hold the last real preference while a single-look style is active so
  // switching away from it lands back where the user was
  useEffect(() => {
    const p = getPaletteForTheme(theme)
    if (p.dark !== p.light) setMode(isLightTheme(theme) ? 'light' : 'dark')
  }, [theme])

  function pickMode(next: 'dark' | 'light') {
    setMode(next)
    setTheme(palette[next])
  }

  function pickPalette(id: string) {
    const next = PALETTES.find((p) => p.id === id)
    if (next) setTheme(next[mode])
  }

  const privacyMode = useAppStore((s) => s.privacyMode)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)
  const navigate = useNavigate()
  const logout = useLogout()
  const { data: me } = useCurrentUser()
  const updateAvailable = useUpdateStatus().data?.update_available === true

  function go(path: string) {
    closeMoreSheet()
    navigate(path)
  }

  return (
    <BottomSheet open={open} onClose={closeMoreSheet} historyKey="more">
      <div className="more-sheet">
        {me && (
          <div className="more-sheet__whoami">
            <UserCircle2 size={16} />
            <span>{me.display_name || me.email}</span>
          </div>
        )}
        <button className="more-sheet__item press-scale" onClick={() => go('/payees')}>
          <Users size={18} />
          <span>Payees</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={() => go('/guide')}>
          <Compass size={18} />
          <span>Guide</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={() => go('/scheduled')}>
          <CalendarClock size={18} />
          <span>Scheduled</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={() => go('/liabilities')}>
          <Landmark size={18} />
          <span>Liabilities</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={() => go('/ai-activity')}>
          <Sparkles size={18} />
          <span>AI Activity</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={() => go('/import')}>
          <Upload size={18} />
          <span>Import</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={() => go('/settings')}>
          <Settings size={18} />
          <span>Settings</span>
          {updateAvailable && (
            <span
              className="more-sheet__update-badge"
              title="Update available — see Settings → Updates"
            />
          )}
        </button>
        <button className="more-sheet__item press-scale" onClick={togglePrivacyMode} aria-pressed={privacyMode}>
          {privacyMode ? <EyeOff size={18} /> : <Eye size={18} />}
          <span>{privacyMode ? 'Show amounts' : 'Hide amounts'}</span>
        </button>
        <button
          className="more-sheet__item press-scale"
          onClick={() => {
            closeMoreSheet()
            clearCurrentBudget()
            navigate('/budgets')
          }}
        >
          <ChevronLeft size={18} />
          <span>Switch budget</span>
        </button>
        <button className="more-sheet__item press-scale" onClick={logout}>
          <LogOut size={18} />
          <span>Sign out</span>
        </button>

        <div className="more-sheet__section-label">
          <Palette size={14} />
          <span>Theme</span>
        </div>
        {/* One mode toggle + one style dropdown instead of a wall of tiles —
            the swatches preview the active theme's real colors, and a
            single-look style (both slots equal) disables the toggle. */}
        <div className="more-sheet__theme-controls">
          <div className="more-sheet__mode" role="group" aria-label="Light or dark mode">
            <button
              className={`more-sheet__mode-btn ${mode === 'dark' && !singleLook ? 'more-sheet__mode-btn--active' : ''}`}
              onClick={() => pickMode('dark')}
              disabled={singleLook}
              aria-pressed={mode === 'dark' && !singleLook}
            >
              <Moon size={14} />
              <span>Dark</span>
            </button>
            <button
              className={`more-sheet__mode-btn ${mode === 'light' && !singleLook ? 'more-sheet__mode-btn--active' : ''}`}
              onClick={() => pickMode('light')}
              disabled={singleLook}
              aria-pressed={mode === 'light' && !singleLook}
            >
              <Sun size={14} />
              <span>Light</span>
            </button>
          </div>
          <label className="more-sheet__palette" data-theme={theme}>
            <span className="more-sheet__theme-swatches" aria-hidden>
              <span className="more-sheet__theme-swatch more-sheet__theme-swatch--accent" />
              <span className="more-sheet__theme-swatch more-sheet__theme-swatch--positive" />
              <span className="more-sheet__theme-swatch more-sheet__theme-swatch--negative" />
            </span>
            <select
              className="more-sheet__palette-select"
              value={palette.id}
              onChange={(e) => pickPalette(e.target.value)}
              aria-label="Theme style"
            >
              {PALETTES.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="more-sheet__palette-chevron" aria-hidden />
          </label>
        </div>
      </div>
    </BottomSheet>
  )
}
