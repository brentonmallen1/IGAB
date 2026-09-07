import { useRef, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { Search } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAnchoredPosition, type AnchorSource } from '../../../hooks/useAnchoredPosition'
import './ContextMenu.css'

/** Matches `.context-menu`'s min-width. The menu sizes to its longest label
 *  above this; the hook measures that and clamps it into the viewport. */
const MENU_MIN_WIDTH = 180

export interface ContextMenuItem {
  id: string
  label: string
  icon?: LucideIcon
  disabled?: boolean
  danger?: boolean
  separator?: boolean
  shortcut?: string
}

interface Props {
  items: ContextMenuItem[]
  onSelect: (id: string) => void
  onClose: () => void
  /** The control the menu hangs off, or the point a right-click happened at. */
  anchor: AnchorSource
  /** Line the menu's right edge up with the anchor instead of its left. */
  alignRight?: boolean
  /**
   * Offer a filter box above the items. Set it for a menu whose length is the
   * user's data rather than the app's design — a budget can have forty
   * category groups, and scrolling forty rows to find one is not finding it.
   * Below `SEARCH_FLOOR` items the box is suppressed anyway: a filter over
   * five things costs more attention than it saves.
   */
  searchable?: boolean
  searchPlaceholder?: string
  className?: string
}

/** Fewer items than this and a filter box is noise. */
const SEARCH_FLOOR = 8

/**
 * A menu, placed by the one rule that places everything else.
 *
 * It used to place itself: `const menuHeight = 280 // conservative estimate`,
 * clamped against a constant that had nothing to do with how many items it was
 * given. A menu is as tall as its items, so a budget with a dozen category
 * groups drew a ~380px menu that the 280px guess happily allowed to run off
 * the bottom — and with no max-height it could not scroll out of the problem
 * either. Two callers had already noticed and were subtracting a magic 160
 * from the anchor to compensate, which made short menus float.
 *
 * Now the panel is measured and `placeAnchored` decides the side. The magic
 * numbers are gone from here and from every caller.
 */
export function ContextMenu({
  items,
  onSelect,
  onClose,
  anchor,
  alignRight,
  searchable,
  searchPlaceholder = 'Search…',
  className = '',
}: Props) {
  const menuRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const showSearch = Boolean(searchable) && items.length >= SEARCH_FLOOR

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    // Separators group a list nobody is reading once it is filtered.
    return items.filter((i) => !i.separator && i.label.toLowerCase().includes(q))
  }, [items, query])
  // No `width`: the hook measures the menu instead, so the clamp knows how
  // wide the longest label actually made it.
  const pos = useAnchoredPosition(
    anchor,
    true,
    { minWidth: MENU_MIN_WIDTH, align: alignRight ? 'end' : 'start', gap: 4 },
    menuRef
  )

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose])

  return createPortal(
    <div
      ref={menuRef}
      className={`context-menu ${className}`}
      style={{
        position: 'fixed',
        top: pos?.top,
        bottom: pos?.bottom,
        left: pos?.left,
        maxHeight: pos?.maxHeight,
        // Hidden until measured: the menu must be in the DOM for its height to
        // be readable, and a menu that paints at 0,0 for one frame reads as a
        // flicker in the corner.
        visibility: pos ? undefined : 'hidden',
      }}
      role="menu"
    >
      {showSearch && (
        <div className="context-menu__search">
          <Search size={12} aria-hidden />
          <input
            autoFocus
            value={query}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              // Enter takes the only thing left, which is what typing three
              // letters and pressing Enter is asking for.
              if (e.key !== 'Enter') return
              const first = shown.find((i) => !i.separator && !i.disabled)
              if (!first) return
              e.preventDefault()
              onSelect(first.id)
              onClose()
            }}
          />
        </div>
      )}
      <div className="context-menu__list">
        {shown.length === 0 && <p className="context-menu__empty">Nothing by that name</p>}
        {shown.map((item) => {
          if (item.separator) {
            return <div key={item.id} className="context-menu__separator" />
          }
          const Icon = item.icon
          return (
            <button
              key={item.id}
              className={`context-menu__item ${item.danger ? 'context-menu__item--danger' : ''} ${item.disabled ? 'context-menu__item--disabled' : ''}`}
              onClick={() => {
                if (!item.disabled) {
                  onSelect(item.id)
                  onClose()
                }
              }}
              disabled={item.disabled}
              role="menuitem"
            >
              {Icon && (
                <span className="context-menu__icon">
                  <Icon size={14} />
                </span>
              )}
              <span className="context-menu__label">{item.label}</span>
              {item.shortcut && <span className="context-menu__shortcut">{item.shortcut}</span>}
            </button>
          )
        })}
      </div>
    </div>,
    document.body
  )
}
