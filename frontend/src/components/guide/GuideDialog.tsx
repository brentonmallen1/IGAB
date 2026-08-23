import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { Modal } from '../common/Modal/Modal'
import { BottomSheet } from '../common/BottomSheet/BottomSheet'

/**
 * A dialog that is a centred panel on a desktop and a bottom sheet on a phone.
 *
 * Both primitives already handle focus trapping, Escape, scroll locking and
 * Android back; this only picks between them so every dialog in the Guide
 * behaves the same way without repeating the branch.
 */
export function GuideDialog({
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
  const isMobile = useIsMobile()

  if (isMobile) {
    return (
      <BottomSheet open onClose={onClose} title={title} historyKey={historyKey}>
        <div className="guide-dialog">{children}</div>
      </BottomSheet>
    )
  }

  return (
    <Modal onClose={onClose} className="guide-dialog__overlay" historyKey={historyKey}>
      <div className="guide-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <div className="guide-dialog__head">
          <h3 className="guide-dialog__title">{title}</h3>
          <button type="button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </Modal>
  )
}
