import { useEffect, useRef, useState, type ReactNode, type TouchEvent } from 'react'
import { createPortal } from 'react-dom'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import './BottomSheet.css'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: string
  /** 'auto' sizes to content (max 85dvh); 'full' takes the whole viewport minus a top gap */
  height?: 'auto' | 'full'
  children: ReactNode
  /** Sticky footer rendered above the safe-area inset */
  footer?: ReactNode
  /** Enables Android-back / swipe-back dismissal via a same-URL history entry */
  historyKey?: string
}

// Body scroll lock + Escape routing must survive nested sheets (e.g. a picker
// sheet opened from inside a full-screen editor sheet), so both are tracked
// module-wide rather than per-instance.
let scrollLockCount = 0
function lockBodyScroll() {
  if (++scrollLockCount === 1) document.body.style.overflow = 'hidden'
}
function unlockBodyScroll() {
  if (--scrollLockCount === 0) document.body.style.overflow = ''
}

const sheetStack: symbol[] = []

const SWIPE_CLOSE_THRESHOLD_PX = 90

export function BottomSheet({
  open,
  onClose,
  title,
  height = 'auto',
  children,
  footer,
  historyKey,
}: BottomSheetProps) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('bottom-sheet')
  const panelRef = useRef<HTMLDivElement>(null)
  const dragStartYRef = useRef<number | null>(null)
  const [dragOffset, setDragOffset] = useState(0)
  // iOS Safari ignores interactive-widget=resizes-content; when the keyboard
  // shrinks the visual viewport, clamp the sheet so the footer stays reachable.
  const [viewportHeight, setViewportHeight] = useState<number | null>(null)

  useHistoryDismissable(Boolean(open && historyKey), onClose, historyKey ?? 'sheet')

  useEffect(() => {
    if (!open) return
    const id = idRef.current!
    sheetStack.push(id)
    lockBodyScroll()

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && sheetStack[sheetStack.length - 1] === id) {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKey)

    return () => {
      document.removeEventListener('keydown', handleKey)
      const idx = sheetStack.indexOf(id)
      if (idx !== -1) sheetStack.splice(idx, 1)
      unlockBodyScroll()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    const vv = window.visualViewport
    if (!vv) return
    const update = () => {
      // Only clamp when the visual viewport is meaningfully smaller (keyboard up)
      setViewportHeight(vv.height < window.innerHeight - 50 ? vv.height : null)
    }
    update()
    vv.addEventListener('resize', update)
    return () => {
      vv.removeEventListener('resize', update)
      setViewportHeight(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    // Don't steal focus from autofocused content (e.g. the quick-add amount field)
    const panel = panelRef.current
    if (panel && !panel.contains(document.activeElement)) panel.focus()
  }, [open])

  if (!open) return null

  const handleTouchStart = (e: TouchEvent) => {
    dragStartYRef.current = e.touches[0].clientY
  }
  const handleTouchMove = (e: TouchEvent) => {
    if (dragStartYRef.current === null) return
    const dy = e.touches[0].clientY - dragStartYRef.current
    setDragOffset(Math.max(0, dy))
  }
  const handleTouchEnd = () => {
    if (dragOffset > SWIPE_CLOSE_THRESHOLD_PX) {
      onClose()
    }
    dragStartYRef.current = null
    setDragOffset(0)
  }

  const panelStyle: React.CSSProperties = {}
  if (dragOffset > 0) {
    panelStyle.transform = `translateY(${dragOffset}px)`
    panelStyle.transition = 'none'
  }
  if (viewportHeight !== null) {
    panelStyle.maxHeight = `${viewportHeight - 12}px`
    if (height === 'full') panelStyle.height = `${viewportHeight - 12}px`
  }

  return createPortal(
    <>
      <div className="bottom-sheet-backdrop" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        className={`bottom-sheet ${height === 'full' ? 'bottom-sheet--full' : ''}`}
        style={panelStyle}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div
          className="bottom-sheet__header"
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
        >
          <div className="bottom-sheet__handle" aria-hidden />
          {title && <div className="bottom-sheet__title">{title}</div>}
        </div>
        <div className="bottom-sheet__body">{children}</div>
        {footer && <div className="bottom-sheet__footer">{footer}</div>}
      </div>
    </>,
    document.body
  )
}
