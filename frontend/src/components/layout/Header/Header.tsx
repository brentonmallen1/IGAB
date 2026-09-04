import { useState, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Moon,
  Palette,
  Search,
  Sun,
} from 'lucide-react'
import {
  useAppStore,
  PALETTES,
  getPaletteForTheme,
  hasBothModes,
  isLightTheme,
} from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { AIActivityBadge } from '../../ai/AIActivityBadge'
import { UndoRedoButtons } from './UndoRedoButtons'
import { IS_MAC } from '../../../keyboard/shortcuts'
import { addMonths, currentMonthStart } from '../../../utils/dates'
import './Header.css'

export function Header() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const budgetAnchorMonth = useAppStore((s) => s.budgetAnchorMonth)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const toggleThemeMode = useAppStore((s) => s.toggleThemeMode)
  const privacyMode = useAppStore((s) => s.privacyMode)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)
  const openPalette = useUIStore((s) => s.openPalette)
  const { formatMonth } = useFormatters()
  const [themeOpen, setThemeOpen] = useState(false)
  const themeRef = useRef<HTMLDivElement>(null)
  // selectedMonth only drives the budget view; elsewhere the nav is dead weight.
  const onBudgetPage = useLocation().pathname === '/budget'

  const canToggleMode = hasBothModes(theme)
  const isLight = canToggleMode && isLightTheme(theme)
  const modeLabel = canToggleMode
    ? isLight
      ? 'Switch to dark mode'
      : 'Switch to light mode'
    : `${getPaletteForTheme(theme).label} has a single look`

  useEffect(() => {
    if (!themeOpen) return
    function handleClick(e: MouseEvent) {
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [themeOpen])

  return (
    <header className="header">
      {onBudgetPage && (
        <div className="header__month-nav">
          <button
            className="header__month-btn"
            onClick={() => setSelectedMonth(addMonths(selectedMonth, -1))}
            aria-label="Previous month"
            // The store clamps anyway (one rule); disabling says so.
            disabled={!!budgetAnchorMonth && selectedMonth <= budgetAnchorMonth}
            title={
              budgetAnchorMonth && selectedMonth <= budgetAnchorMonth
                ? 'Your budget starts here — earlier months live in the register and reports'
                : undefined
            }
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
          {selectedMonth !== currentMonthStart() && (
            <button
              className="header__today-btn"
              onClick={() => setSelectedMonth(currentMonthStart())}
              title="Go to current month"
              aria-label="Go to current month"
            >
              <CalendarDays size={14} />
            </button>
          )}
        </div>
      )}

      <AIActivityBadge />

      <div className="header__palette-wrap">
        <button
          className="header__palette-btn"
          onClick={openPalette}
          aria-label="Open command palette"
          aria-keyshortcuts={IS_MAC ? 'Meta+K' : 'Control+K'}
        >
          <Search size={13} />
          <span className="header__palette-text">Search or jump to…</span>
          <kbd className="kbd">{IS_MAC ? '⌘' : 'Ctrl+'}K</kbd>
        </button>
      </div>

      <UndoRedoButtons />

      <button
        className={`header__icon-btn ${privacyMode ? 'header__icon-btn--active' : ''}`}
        onClick={togglePrivacyMode}
        aria-pressed={privacyMode}
        aria-label={privacyMode ? 'Show amounts' : 'Hide amounts (privacy mode)'}
        title={privacyMode ? 'Show amounts' : 'Hide amounts (privacy mode)'}
      >
        {privacyMode ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>

      <button
        className="header__icon-btn"
        onClick={toggleThemeMode}
        disabled={!canToggleMode}
        aria-label={modeLabel}
        title={modeLabel}
      >
        {isLight ? <Moon size={16} /> : <Sun size={16} />}
      </button>

      <div className="header__theme-picker" ref={themeRef}>
        <button
          className="header__icon-btn"
          onClick={() => setThemeOpen((o) => !o)}
          aria-label="Change theme"
          title="Change theme"
        >
          <Palette size={16} />
        </button>
        {themeOpen && (
          <div className="header__theme-dropdown">
            {PALETTES.map((p) => (
              <button
                key={p.id}
                className={`header__theme-option ${
                  p.id === getPaletteForTheme(theme).id ? 'header__theme-option--active' : ''
                }`}
                onClick={() => {
                  // Keep the mode the user is in — the palette list only swaps style
                  setTheme(isLightTheme(theme) ? p.light : p.dark)
                  setThemeOpen(false)
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  )
}
