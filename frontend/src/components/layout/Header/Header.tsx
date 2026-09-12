import { useState, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Bot,
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
import { useAIStatus } from '../../../api/ai'
import { useFormatters } from '../../../hooks/useFormatters'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { UndoRedoButtons } from './UndoRedoButtons'
import { IS_MAC } from '../../../keyboard/shortcuts'
import { addMonths, currentMonthStart } from '../../../utils/dates'
import { PAGE_HEADER_SLOT_ID } from '../../common/PageHeader/PageHeader'
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
  const chatPanelOpen = useUIStore((s) => s.chatPanelOpen)
  const toggleChatPanel = useUIStore((s) => s.toggleChatPanel)
  // Render-gated, not hook-gated: react-hooks/rules-of-hooks is an error here,
  // and a component whose hook count changes between renders is broken.
  const { data: aiStatus } = useAIStatus()
  const { formatMonth } = useFormatters()
  const [themeOpen, setThemeOpen] = useState(false)
  const themeRef = useRef<HTMLDivElement>(null)
  // selectedMonth only drives the budget view; elsewhere the nav is dead weight.
  const onBudgetPage = useLocation().pathname === '/budget'
  // On a phone the header keeps the month nav, search and the assistant,
  // nothing else. Nine 44px controls in 342px shrank every one of them, hid the
  // search button outright and clipped the theme picker at the edge; privacy,
  // light/dark and the palette already live in the More sheet, and undo/redo
  // join it there.
  const isMobile = useIsMobile()

  // One element, placed by layout: beside search on a phone, among the desktop
  // controls otherwise. The assistant is something you reach for while looking
  // at a figure, so on a phone it earns a header slot rather than a trip
  // through More.
  const chatLabel = chatPanelOpen ? 'Close the assistant' : 'Ask about your budget'
  const chatButton =
    aiStatus?.enabled === true ? (
      <button
        className={`header__icon-btn ${chatPanelOpen ? 'header__icon-btn--active' : ''}`}
        onClick={toggleChatPanel}
        aria-pressed={chatPanelOpen}
        aria-label={chatLabel}
        title={chatLabel}
      >
        <Bot size={16} />
      </button>
    ) : null

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
                ? 'Your budget starts here. Earlier months are in each account\u2019s register and in Reports.'
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

      {/* On a phone, a page's PageHeader portals its title and back chevron
          here, so the page spends no band of its own on a name the nav
          already states. Empty on the budget route, which has the month. */}
      {!onBudgetPage && isMobile && <div id={PAGE_HEADER_SLOT_ID} className="header__page-slot" />}

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

      {isMobile && chatButton}

      {!isMobile && (
        <>
          <UndoRedoButtons />

          {chatButton}

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
        </>
      )}
    </header>
  )
}
