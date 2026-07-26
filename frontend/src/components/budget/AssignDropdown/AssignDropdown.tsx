import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { Zap } from 'lucide-react'
import { useAssignStrategyTotals } from '../../../api/assign'
import type { AssignStrategy } from '../../../types'
import { AssignAutoTab } from './AssignAutoTab'
import { AssignManualTab } from './AssignManualTab'
import './AssignDropdown.css'

type Tab = 'auto' | 'manual'

interface ContentProps {
  budgetId: string
  month: string
  tba: number
  onPickStrategy: (strategy: AssignStrategy) => void
  onCoverOverspent: () => void
  onClose: () => void
}

/**
 * The dropdown's inner content — tabs plus the active pane. Shared between
 * the desktop anchored panel and the mobile bottom sheet.
 */
export function AssignDropdownContent({
  budgetId,
  month,
  tba,
  onPickStrategy,
  onCoverOverspent,
  onClose,
}: ContentProps) {
  const [tab, setTab] = useState<Tab>('auto')
  const rootRef = useRef<HTMLDivElement>(null)
  const { data: totals, isLoading } = useAssignStrategyTotals(budgetId, month, true)

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      onClose()
      return
    }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      // Don't hijack arrows while typing in the manual form
      if ((e.target as HTMLElement).tagName === 'INPUT') return
      setTab((t) => (t === 'auto' ? 'manual' : 'auto'))
      return
    }
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && tab === 'auto') {
      e.preventDefault()
      const rows = Array.from(
        rootRef.current?.querySelectorAll<HTMLButtonElement>('[data-assign-row]:not(:disabled)') ??
          []
      )
      if (rows.length === 0) return
      const idx = rows.findIndex((r) => r === document.activeElement)
      const next =
        e.key === 'ArrowDown'
          ? rows[Math.min(idx + 1, rows.length - 1)]
          : rows[Math.max(idx - 1, 0)]
      next?.focus()
    }
  }

  return (
    <div ref={rootRef} className="assign-dropdown__content" onKeyDown={handleKeyDown}>
      <div className="assign-dropdown__tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'auto'}
          className={`assign-dropdown__tab ${tab === 'auto' ? 'assign-dropdown__tab--active' : ''}`}
          onClick={() => setTab('auto')}
        >
          <Zap size={13} />
          Auto
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'manual'}
          className={`assign-dropdown__tab ${tab === 'manual' ? 'assign-dropdown__tab--active' : ''}`}
          onClick={() => setTab('manual')}
        >
          Manually
        </button>
      </div>
      {tab === 'auto' ? (
        <AssignAutoTab
          totals={totals}
          isLoading={isLoading}
          onPickStrategy={onPickStrategy}
          onCoverOverspent={onCoverOverspent}
        />
      ) : (
        <AssignManualTab budgetId={budgetId} month={month} tba={tba} onDone={onClose} />
      )}
    </div>
  )
}

interface DropdownProps extends ContentProps {
  anchorRef: RefObject<HTMLElement | null>
}

const PANEL_WIDTH = 320
const VIEWPORT_MARGIN = 8

/** Desktop: fixed-position portal panel anchored under the Assign button. */
export function AssignDropdown({ anchorRef, onClose, ...contentProps }: DropdownProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useEffect(() => {
    const rect = anchorRef.current?.getBoundingClientRect()
    if (rect) {
      setPos({
        top: rect.bottom + 6,
        left: Math.max(
          VIEWPORT_MARGIN,
          Math.min(rect.left, window.innerWidth - PANEL_WIDTH - VIEWPORT_MARGIN)
        ),
      })
    }
  }, [anchorRef])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      const t = e.target as Node
      if (!panelRef.current?.contains(t) && !anchorRef.current?.contains(t)) {
        onClose()
      }
    }
    function handleKey(e: globalThis.KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose, anchorRef])

  if (!pos) return null

  return createPortal(
    <div
      ref={panelRef}
      className="assign-dropdown"
      style={{ position: 'fixed', top: pos.top, left: pos.left, width: PANEL_WIDTH }}
      role="dialog"
      aria-label="Assign money"
    >
      <AssignDropdownContent onClose={onClose} {...contentProps} />
    </div>,
    document.body
  )
}
