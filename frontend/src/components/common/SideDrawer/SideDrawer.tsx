import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import { isTopOverlay, popOverlay, pushOverlay } from '../../../utils/overlayStack'
import './SideDrawer.css'

/**
 * A panel docked to the right edge, beside the page rather than over it.
 *
 * Not a Modal on purpose: it has no backdrop, because the page behind stays
 * live — the attachments drawer opens from a register row and the next row
 * must still be selectable while it is up. Everything else an overlay owes
 * (a visible close at the tap floor, Escape through the overlay stack so a
 * dialog raised from inside it closes first, a history entry so Android back
 * works) it has. Desktop only by convention: on a phone a docked panel is
 * the whole screen, and the caller shows a full BottomSheet instead.
 */
export function SideDrawer({
  title,
  onClose,
  historyKey,
  children,
}: {
  title: string
  onClose: () => void
  historyKey: string
  children: ReactNode
}) {
  const idRef = useRef<symbol | null>(null)
  if (idRef.current === null) idRef.current = Symbol('side-drawer')
  const panelRef = useFocusTrap<HTMLDivElement>(undefined, {
    initialFocus: (): HTMLElement | false => panelRef.current ?? false,
  })
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })
  const requestClose = () => onCloseRef.current()
  useHistoryDismissable(true, requestClose, historyKey)

  useEffect(() => {
    const id = idRef.current!
    pushOverlay(id)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isTopOverlay(id)) {
        e.stopPropagation()
        onCloseRef.current()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      popOverlay(id)
    }
  }, [])

  return createPortal(
    <div
      ref={panelRef}
      className="side-drawer"
      role="dialog"
      aria-modal="false"
      aria-label={title}
      tabIndex={-1}
    >
      <div className="side-drawer__header">
        <span className="side-drawer__title">{title}</span>
        <button
          type="button"
          className="side-drawer__close"
          onClick={requestClose}
          aria-label="Close"
        >
          <X size={16} />
        </button>
      </div>
      <div className="side-drawer__body">{children}</div>
    </div>,
    document.body
  )
}
