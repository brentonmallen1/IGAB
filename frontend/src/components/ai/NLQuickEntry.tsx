import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { useAIStatus } from '../../api/ai'
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
 * Natural-language transaction entry as a standalone overlay (mobile
 * quick-add): type or dictate, and the parsed draft opens in the normal
 * add-transaction editor — one flow regardless of how the words got here.
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
    <div
      className="nl-entry-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="nl-entry" role="dialog" aria-modal aria-label="AI transaction entry">
        <div className="nl-entry__header">
          <Sparkles size={14} />
          <span>Describe a transaction</span>
          <button className="nl-entry__close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <NLEntryForm budgetId={budgetId} onDraft={setEditorDraft} onNavigate={onClose} />
      </div>
    </div>
  )
}
