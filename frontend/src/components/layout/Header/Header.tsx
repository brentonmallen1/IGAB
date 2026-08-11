import { useState, useRef, useEffect } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, Eye, EyeOff, Moon, Palette, Search, Sun } from 'lucide-react'
import { useAppStore, PALETTES, getPaletteForTheme, isLightTheme } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { AIActivityBadge } from '../../ai/AIActivityBadge'
import { IS_MAC } from '../../../keyboard/shortcuts'
import { addMonths, currentMonthStart } from '../../../utils/dates'
import './Header.css'

export function Header() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const privacyMode = useAppStore((s) => s.privacyMode)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)
  const openPalette = useUIStore((s) => s.openPalette)
  const { formatMonth } = useFormatters()
  const [themeOpen, setThemeOpen] = useState(false)
  const themeRef = useRef<HTMLDivElement>(null)

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

      <button
        className={`header__privacy-btn ${privacyMode ? 'header__privacy-btn--active' : ''}`}
        onClick={togglePrivacyMode}
        aria-pressed={privacyMode}
        aria-label={privacyMode ? 'Show amounts' : 'Hide amounts (privacy mode)'}
        title={privacyMode ? 'Show amounts' : 'Hide amounts (privacy mode)'}
      >
        {privacyMode ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>

      <div className="header__theme-picker" ref={themeRef}>
        <button
          className="header__theme-btn"
          onClick={() => setThemeOpen((o) => !o)}
          aria-label="Change theme"
          title="Change theme"
        >
          <Palette size={16} />
        </button>
        {themeOpen && (
          <div className="header__theme-dropdown">
            <div className="header__theme-toggle">
              {(() => {
                const currentPalette = getPaletteForTheme(theme)
                const isLight = isLightTheme(theme)
                const hasBothVariants = currentPalette.dark !== currentPalette.light
                return (
                  <>
                    <button
                      className={`header__theme-mode ${!isLight ? 'header__theme-mode--active' : ''}`}
                      onClick={() => setTheme(currentPalette.dark)}
                      disabled={!hasBothVariants}
                      aria-label="Dark mode"
                    >
                      <Moon size={14} />
                      <span>Dark</span>
                    </button>
                    <button
                      className={`header__theme-mode ${isLight ? 'header__theme-mode--active' : ''}`}
                      onClick={() => setTheme(currentPalette.light)}
                      disabled={!hasBothVariants}
                      aria-label="Light mode"
                    >
                      <Sun size={14} />
                      <span>Light</span>
                    </button>
                  </>
                )
              })()}
            </div>
            <div className="header__theme-divider" />
            {PALETTES.map((p) => {
              const currentPalette = getPaletteForTheme(theme)
              const isActive = p.id === currentPalette.id
              return (
                <button
                  key={p.id}
                  className={`header__theme-option ${isActive ? 'header__theme-option--active' : ''}`}
                  onClick={() => {
                    const useLight = isLightTheme(theme)
                    setTheme(useLight ? p.light : p.dark)
                    setThemeOpen(false)
                  }}
                >
                  {p.label}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </header>
  )
}
