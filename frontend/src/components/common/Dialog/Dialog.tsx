import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { Modal } from '../Modal/Modal'
import { BottomSheet } from '../BottomSheet/BottomSheet'
import './Dialog.css'

/**
 * A dialog that is a centred panel on a desktop and a bottom sheet on a phone.
 *
 * `Modal` and `BottomSheet` already handle focus trapping, Escape, the overlay
 * stack, scroll locking and Android back; this picks between them and supplies
 * the panel itself — the header, the close control, and the one scroll region —
 * so a dialog does not have to be assembled from primitives each time. Six
 * components in this repo hand-rolled their own overlay and copied `.overlay`'s
 * CSS into a private class; this is the shape that stops the seventh.
 *
 * Painting is by role, never by `--bg-*`: the panel is `--surface-overlay` and
 * anything inset within it should be a `<Surface variant="sunken">`. A dialog
 * whose sections all share one background is one nobody can read.
 */
export function Dialog({
  title,
  onClose,
  historyKey,
  className,
  footer,
  width = 'md',
  children,
}: {
  title: string
  onClose: () => void
  historyKey: string
  /** Extra class on the panel, for callers with their own tokens to set. */
  className?: string
  /** Pinned below the scroll region — actions stay reachable on a long body. */
  footer?: ReactNode
  /** 'md' suits prose and a short list; 'lg' a table the user reads across. */
  width?: 'md' | 'lg'
  children: ReactNode
}) {
  const isMobile = useIsMobile()
  const panel = ['dialog', `dialog--${width}`, className].filter(Boolean).join(' ')

  if (isMobile) {
    return (
      <BottomSheet
        open
        onClose={onClose}
        title={title}
        historyKey={historyKey}
        height="full"
        footer={footer}
      >
        <div className={panel}>{children}</div>
      </BottomSheet>
    )
  }

  return (
    <Modal onClose={onClose} className="dialog__overlay" historyKey={historyKey}>
      <div className={panel} role="dialog" aria-modal="true" aria-label={title}>
        <div className="dialog__head">
          <h3 className="dialog__title">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="dialog__scroll">{children}</div>
        {footer && <div className="dialog__footer">{footer}</div>}
      </div>
    </Modal>
  )
}
