import { useState } from 'react'
import { ClipboardCheck } from 'lucide-react'
import { useImportSummary } from '../../../api/imports'
import { ImportReviewDialog } from './ImportReviewDialog'
import './ImportReviewDialog.css'

/**
 * Reopen the import review on demand.
 *
 * The same dialog the gate opens after an import, reached deliberately. It is
 * worth having for a budget that never saw one: everything imported before the
 * review existed carries the tags the importer guessed and nothing has ever
 * shown them, and a budget built by hand has no tags at all — the suggestions
 * are the only reason its Essentials report is empty.
 */
export function ImportReviewButton({ budgetId }: { budgetId: string | null }) {
  const [open, setOpen] = useState(false)
  const { data } = useImportSummary(budgetId)

  if (!budgetId) return null

  return (
    <>
      <button type="button" className="import-review__btn" onClick={() => setOpen(true)}>
        <ClipboardCheck size={14} />
        Review tags
      </button>
      {open && (
        <ImportReviewDialog
          budgetId={budgetId}
          summary={data?.summary ?? null}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
