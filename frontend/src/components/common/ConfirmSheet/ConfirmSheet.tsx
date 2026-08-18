import { BottomSheet } from '../BottomSheet/BottomSheet'
import './ConfirmSheet.css'

interface ConfirmSheetProps {
  open: boolean
  title: string
  /** Optional detail line under the title. */
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  /** Styles the confirm action as destructive (discard, delete). */
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * In-app replacement for window.confirm on touch.
 *
 * A native confirm is unusable mid-entry on iOS: it blurs the focused field,
 * tears down the keyboard, retriggers a viewport resize in the middle of a
 * dismissal, and in an installed PWA renders with the app's origin in the
 * title. This is a plain sheet, so it composes with the overlay stack and the
 * keyboard-aware anchoring like everything else.
 */
export function ConfirmSheet({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmSheetProps) {
  return (
    <BottomSheet open={open} onClose={onCancel} title={title}>
      <div className="confirm-sheet">
        {message && <p className="confirm-sheet__message">{message}</p>}
        <div className="confirm-sheet__actions">
          <button
            type="button"
            className={`confirm-sheet__confirm press-scale ${destructive ? 'confirm-sheet__confirm--destructive' : ''}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
          <button type="button" className="confirm-sheet__cancel press-scale" onClick={onCancel}>
            {cancelLabel}
          </button>
        </div>
      </div>
    </BottomSheet>
  )
}
