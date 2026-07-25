import { useState, useRef, useEffect } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight, Palette, Search } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { IS_MAC } from '../../../keyboard/shortcuts'
import { formatMonth, addMonths, currentMonthStart } from '../../../utils/dates'
import type { Theme } from '../../../stores/appStore'
import './Header.css'

export const THEMES: { value: Theme; label: string }[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'gruvbox-dark', label: 'Gruvbox Dark' },
  { value: 'gruvbox-light', label: 'Gruvbox Light' },
  { value: 'catppuccin-mocha', label: 'Catppuccin Mocha' },
  { value: 'catppuccin-latte', label: 'Catppuccin Latte' },
  { value: 'rose-pine', label: 'Rosé Pine' },
  { value: 'rose-pine-moon', label: 'Rosé Pine Moon' },
  { value: 'nord', label: 'Nord' },
]

export function Header() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const openPalette = useUIStore((s) => s.openPalette)
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
            {THEMES.map((t) => (
              <button
                key={t.value}
                className={`header__theme-option ${theme === t.value ? 'header__theme-option--active' : ''}`}
                onClick={() => { setTheme(t.value); setThemeOpen(false) }}
              >
                {t.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  )
}
