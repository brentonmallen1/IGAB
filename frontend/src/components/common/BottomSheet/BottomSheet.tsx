import { useCallback, useEffect, useRef, useState, type ReactNode, type TouchEvent } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { lockBodyScroll, unlockBodyScroll } from '../../../utils/scrollLock'
import { isTopOverlay, popOverlay, pushOverlay } from '../../../utils/overlayStack'
import { hapticTick } from '../../../utils/haptics'
import { shouldDismissDrag } from './dismissDrag'
import './BottomSheet.css'

interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: string
  /** 'auto' sizes to content (max 85% of the visible viewport); 'full' takes it all minus a top gap */
  height?: 'auto' | 'full'
  children: ReactNode
  /** Sticky footer rendered above the safe-area inset */
  footer?: ReactNode
  /** Enables Android-back / swipe-back dismissal via a same-URL history entry */
  historyKey?: string
  /**
   * Synchronous veto run before every dismissal — backdrop, close button,
   * Escape, swipe, and the history pop. Return false to keep the sheet open
   * (e.g. to raise an unsaved-changes confirmation first).
   */
  canClose?: () => boolean
  /** Accessible label for the close button. Defaults to "Close". */
  closeLabel?: string
}

// Matches --transition-base (200ms) with headroom; fallback in case
// animationend never fires (element removed mid-animation, tab backgrounded).
const EXIT_FALLBACK_MS = 300

const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/**
 * Gate: owns only the exit animation, so the panel below it mounts and
 * unmounts with the sheet.
 *
 * That split is load-bearing, not cosmetic. useFocusTrap activates once on
 * mount and reads ref.current immediately — a component that stays mounted and
 * renders null while closed would activate the trap against a null element and
 * never trap anything. It also keeps a closed sheet from re-rendering on its
 * consumers' query updates.
 */
export function BottomSheet({ open, ...rest }: BottomSheetProps) {
  const [closing, setClosing] = useState(false)
  const wasOpenRef = useRef(false)

  useEffect(() => {
    if (open) {
      wasOpenRef.current = true
      setClosing(false)
      return
    }
    if (!wasOpenRef.current) return
    wasOpenRef.current = false
    if (prefersReducedMotion()) return
    setClosing(true)
    const t = setTimeout(() => setClosing(false), EXIT_FALLBACK_MS)
    return () => clearTimeout(t)
  }, [open])

  if (!open && !closing) return null

  return (
    <BottomSheetPanel
      {...rest}
      closing={!open}
      onExited={() => setClosing(false)}
    />
  )
}

function BottomSheetPanel({
  onClose,
  title,
  height = 'auto',
  children,
  footer,
  historyKey,
  canClose,
  closeLabel = 'Close',
  closing,
  onExited,
}: Omit<BottomSheetProps, 'open'> & { closing: boolean; onExited: () => void }) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('bottom-sheet')

  // Evaluated when the trap activates, not at render: yield to content that
  // autofocused its own field (the quick-add amount) — stealing that focus
  // would close the keyboard the user is about to type into — but otherwise
  // move focus into the sheet so screen readers announce it.
  const panelRef = useFocusTrap<HTMLDivElement>(undefined, {
    // Return type annotated to break the self-reference in inference.
    initialFocus: (): HTMLElement | false => {
      const panel = panelRef.current
      if (!panel) return false
      return panel.contains(document.activeElement) ? false : panel
    },
  })

  // Written in an effect, not during render: the handlers below only read
  // these after a user interaction, which is always after commit.
  const onCloseRef = useRef(onClose)
  const canCloseRef = useRef(canClose)
  useEffect(() => {
    onCloseRef.current = onClose
    canCloseRef.current = canClose
  })

  /** Runs the veto, then closes. Returns whether the sheet actually closed. */
  const requestClose = useCallback((): boolean => {
    if (canCloseRef.current && !canCloseRef.current()) return false
    onCloseRef.current()
    return true
  }, [])

  useHistoryDismissable(Boolean(!closing && historyKey), onClose, historyKey ?? 'sheet', canClose)

  useEffect(() => {
    const id = idRef.current!
    pushOverlay(id)
    lockBodyScroll()

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isTopOverlay(id)) {
        e.stopPropagation()
        requestClose()
      }
    }
    document.addEventListener('keydown', handleKey)

    return () => {
      document.removeEventListener('keydown', handleKey)
      popOverlay(id)
      unlockBodyScroll()
    }
  }, [requestClose])

  // A full-height sheet gets a real close button instead of a drag handle. Its
  // header is a sliver of a tall sheet, so the dismissal drag is most of the
  // available travel and reads as stuck — and a downward drag near the top of
  // a scrollable sheet is far more often an intended scroll, which the header's
  // touch-action: none silently swallows. On a short 'auto' sheet the gesture
  // is natural and the travel is short, so it stays.
  const draggable = height === 'auto'

  const dragRef = useRef<{ y: number; t: number } | null>(null)
  const dragYRef = useRef(0)
  const primedRef = useRef(false)

  const handleTouchStart = (e: TouchEvent) => {
    dragRef.current = { y: e.touches[0].clientY, t: performance.now() }
    dragYRef.current = 0
    primedRef.current = false
  }

  const handleTouchMove = (e: TouchEvent) => {
    const start = dragRef.current
    const panel = panelRef.current
    if (!start || !panel) return
    const dy = Math.max(0, e.touches[0].clientY - start.y)
    dragYRef.current = dy
    // Written straight to the element: routing this through state re-rendered
    // the entire sheet — and its consumers' query subscriptions — every frame.
    panel.style.transition = 'none'
    panel.style.transform = `translateY(${dy}px)`

    // Preview the outcome mid-gesture rather than on release; that is what
    // makes drag-to-dismiss feel physical. (Android only — iOS has no
    // vibration API.)
    if (!primedRef.current && shouldDismissDrag(dy, performance.now() - start.t)) {
      primedRef.current = true
      hapticTick()
    }
  }

  const handleTouchEnd = () => {
    const start = dragRef.current
    const panel = panelRef.current
    dragRef.current = null
    if (!start || !panel) return

    const dy = dragYRef.current
    const snapBack = () => {
      panel.style.transition = ''
      panel.style.transform = ''
    }

    if (shouldDismissDrag(dy, performance.now() - start.t)) {
      // Let the exit animation continue from wherever the finger left it.
      panel.style.setProperty('--sheet-drag-y', `${dy}px`)
      if (!requestClose()) snapBack()
    } else {
      snapBack()
    }
  }

  const handleAnimationEnd = (e: React.AnimationEvent) => {
    if (closing && e.animationName === 'bottom-sheet-drop') onExited()
  }

  const dragHandlers = draggable
    ? { onTouchStart: handleTouchStart, onTouchMove: handleTouchMove, onTouchEnd: handleTouchEnd }
    : {}

  // Backdrop and panel share one positioned layer so each sheet is a single
  // stacking context. Nesting then resolves by DOM (mount) order, which is
  // what makes a confirmation raised from inside a sheet dim the sheet under
  // it — with per-element z-indexes the inner backdrop sat behind the outer
  // panel no matter the order.
  return createPortal(
    <div className={`bottom-sheet-layer ${closing ? 'bottom-sheet-layer--closing' : ''}`}>
      <div
        className={`bottom-sheet-backdrop ${closing ? 'bottom-sheet-backdrop--closing' : ''}`}
        onClick={closing ? undefined : () => requestClose()}
        aria-hidden
      />
      <div
        ref={panelRef}
        className={`bottom-sheet ${height === 'full' ? 'bottom-sheet--full' : ''} ${closing ? 'bottom-sheet--closing' : ''}`}
        onAnimationEnd={handleAnimationEnd}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div
          className={`bottom-sheet__header ${draggable ? 'bottom-sheet__header--draggable' : ''}`}
          {...dragHandlers}
        >
          {draggable && <div className="bottom-sheet__handle" aria-hidden />}
          {/* Omitted entirely for a handle-only sheet, which would otherwise
              reserve a tap-target's worth of empty header. */}
          {(!draggable || title) && (
            <div className="bottom-sheet__bar">
              {!draggable && (
                <button
                  type="button"
                  className="bottom-sheet__close"
                  onClick={() => requestClose()}
                  aria-label={closeLabel}
                >
                  <X size={20} />
                </button>
              )}
              {title && <div className="bottom-sheet__title">{title}</div>}
            </div>
          )}
        </div>
        <div className="bottom-sheet__body">{children}</div>
        {footer && <div className="bottom-sheet__footer">{footer}</div>}
      </div>
    </div>,
    document.body
  )
}
