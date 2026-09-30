import { Dialog } from '../common/Dialog/Dialog'
import { NLEntryForm } from './NLEntryForm'
import './NLQuickEntry.css'

interface Props {
  budgetId: string
  /** The account quick add chose; null and the entry waits in AI Activity. */
  accountId?: string | null
  /** Dismissed without sending — back to where it was opened from. */
  onClose: () => void
  /** Sent, or leaving for Settings: the host is done too. */
  onDone: () => void
}

/**
 * Natural-language transaction entry as a dialog (mobile quick-add): type or
 * dictate, send, and put the phone away — the words are read in the
 * background like a scanned receipt, and the row arrives to review. A
 * Dialog, so on a phone it is a sheet with a close button, a history entry
 * and drag-to-dismiss like every other overlay.
 */
export function NLQuickEntry({ budgetId, accountId = null, onClose, onDone }: Props) {
  return (
    <Dialog
      title="Describe a transaction"
      onClose={onClose}
      historyKey="nl-entry"
      className="nl-entry"
    >
      <NLEntryForm
        budgetId={budgetId}
        accountId={accountId}
        onQueued={onDone}
        onNavigate={onDone}
      />
    </Dialog>
  )
}
