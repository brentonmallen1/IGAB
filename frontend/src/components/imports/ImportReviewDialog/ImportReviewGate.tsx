import { useState } from 'react'
import { useImportSummary } from '../../../api/imports'
import { ImportReviewDialog } from './ImportReviewDialog'

/**
 * Opens the import review once, after an import, and never again unasked.
 *
 * The just-imported path and the reopened-from-Settings path are the same
 * dialog reading the same two sources — the stored summary for what happened,
 * the live budget for what can still be changed. Only the trigger differs,
 * which is why this is a gate rather than a second dialog.
 *
 * `reviewed_at` is the whole condition. A budget imported before IGAB kept a
 * record has a null summary and a null timestamp, so it offers its review the
 * first time it is opened — which is the point: those are the budgets with no
 * tags at all.
 */
export function ImportReviewGate({ budgetId }: { budgetId: string | null }) {
  const { data } = useImportSummary(budgetId)
  const [dismissed, setDismissed] = useState(false)

  // Nothing to say and nothing was imported: this budget was made by hand, so
  // opening a review of an import that never happened would be noise.
  if (!budgetId || !data || data.reviewed_at || !data.summary || dismissed) return null

  return (
    <ImportReviewDialog
      budgetId={budgetId}
      summary={data.summary}
      onClose={() => setDismissed(true)}
    />
  )
}
