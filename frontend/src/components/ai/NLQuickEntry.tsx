import { useState } from 'react'
import { useAIStatus } from '../../api/ai'
import { Dialog } from '../common/Dialog/Dialog'
import { NLEntryForm } from './NLEntryForm'
import {
  TransactionEditor,
  type EditorDraft,
} from '../transactions/TransactionEditor/TransactionEditor'
import './NLQuickEntry.css'

interface Props {
  budgetId: string
  /** Fixed account context when opened from an account register. */
  accountId?: string | null
  onClose: () => void
}

/**
 * Natural-language transaction entry as a dialog (mobile quick-add): type or
 * dictate, and the parsed draft opens in the normal add-transaction editor —
 * one flow regardless of how the words got here. A Dialog, so on a phone it
 * is a sheet with a close button, a history entry and drag-to-dismiss like
 * every other overlay, instead of a hand-rolled panel whose only exit was
 * a 16px icon.
 */
export function NLQuickEntry({ budgetId, accountId = null, onClose }: Props) {
  const aiStatus = useAIStatus()
  const [editorDraft, setEditorDraft] = useState<EditorDraft | null>(null)

  if (editorDraft) {
    return (
      <TransactionEditor
        budgetId={budgetId}
        accountId={accountId}
        transaction={null}
        initialDraft={editorDraft}
        onClose={() => {
          setEditorDraft(null)
          onClose()
        }}
      />
    )
  }

  if (aiStatus.data && !aiStatus.data.available) return null

  return (
    <Dialog
      title="Describe a transaction"
      onClose={onClose}
      historyKey="nl-entry"
      className="nl-entry"
    >
      <NLEntryForm budgetId={budgetId} onDraft={setEditorDraft} onNavigate={onClose} />
    </Dialog>
  )
}
