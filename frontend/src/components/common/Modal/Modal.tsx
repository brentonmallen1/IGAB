import { useCallback, useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import { lockBodyScroll, unlockBodyScroll } from '../../../utils/scrollLock'
import { isTopOverlay, popOverlay, pushOverlay } from '../../../utils/overlayStack'
import './Modal.css'

interface ModalProps {
  onClose: () => void
  children: ReactNode
  /** Extra class on the overlay, for per-modal alignment and padding. */
  className?: string
  /** Enables Android-back / swipe-back dismissal via a same-URL history entry. */
  historyKey?: string
  /** Synchronous veto run before every dismissal. Return false to stay open. */
  canClose?: () => boolean
  /** Set false for a modal that must be answered (destructive confirmations). */
  dismissOnBackdrop?: boolean
}

/**
 * The shared overlay layer: portal, focus trap, Escape routing, body scroll
 * lock, scroll containment, and keyboard-aware sizing.
 *
 * Deliberately does NOT render the panel. Consumers own their own panel
 * element — several are <form>s — and keep `role="dialog" aria-modal` on it,
 * which is where those attributes belong. This is a behaviour primitive, not
 * a layout one.
 *
 * Mount it conditionally (`{open && <Modal …>}`): the focus trap activates on
 * mount, so a Modal that stays mounted and renders null would never trap.
 */
export function Modal({
  onClose,
  children,
  className = '',
  historyKey,
  canClose,
  dismissOnBackdrop = true,
}: ModalProps) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('modal')

  // Focus the container rather than the first field: focusing an input would
  // raise the keyboard the instant a modal opens on a phone. Content that
  // genuinely wants a field focused can autofocus it, which this yields to.
  const overlayRef = useFocusTrap<HTMLDivElement>(undefined, {
    // Return type annotated to break the self-reference in inference.
    initialFocus: (): HTMLElement | false => {
      const el = overlayRef.current
      if (!el) return false
      return el.contains(document.activeElement) ? false : el
    },
  })

  const onCloseRef = useRef(onClose)
  const canCloseRef = useRef(canClose)
  useEffect(() => {
    onCloseRef.current = onClose
    canCloseRef.current = canClose
  })

  const requestClose = useCallback((): boolean => {
    if (canCloseRef.current && !canCloseRef.current()) return false
    onCloseRef.current()
    return true
  }, [])

  useHistoryDismissable(Boolean(historyKey), onClose, historyKey ?? 'modal', canClose)

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

  // A backdrop dismissal requires press AND release on the backdrop. Checking
  // only the click target dismisses the modal when a text selection that began
  // inside the panel happens to end outside it.
  const pressedBackdropRef = useRef(false)

  return createPortal(
    <div
      ref={overlayRef}
      className={`overlay ${className}`}
      tabIndex={-1}
      onMouseDown={(e) => {
        pressedBackdropRef.current = e.target === e.currentTarget
      }}
      onClick={(e) => {
        const onBackdrop = e.target === e.currentTarget && pressedBackdropRef.current
        pressedBackdropRef.current = false
        if (onBackdrop && dismissOnBackdrop) requestClose()
      }}
    >
      {children}
    </div>,
    document.body
  )
}
