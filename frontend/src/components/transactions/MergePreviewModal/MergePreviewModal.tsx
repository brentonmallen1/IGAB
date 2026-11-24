import { useState } from 'react'
import { apiErrorMessage } from '../../../api/client'
import { useMergePreview } from '../../../api/transactions'
import type { MergeKeep, Transaction } from '../../../types'
import { Dialog } from '../../common/Dialog/Dialog'
import type { NamedCategory } from '../../../utils/categoryLabels'
import { MergePair } from '../MergePair/MergePair'
import { pairLabels } from '../MergePair/mergePicks'
import './MergePreviewModal.css'

interface Props {
  budgetId: string
  transactions: [Transaction, Transaction]
  payeeMap: ReadonlyMap<string, string>
  categoryLabels: ReadonlyMap<string, NamedCategory>
  /** Both rows are on one account (`mayOfferMerge`); is it on budget? The
   *  category reads by the register's rule, which needs to know. */
  accountOnBudget: boolean
  /** Merge, with the picks the preview was showing. */
  onConfirm: (keep: MergeKeep) => void
  onCancel: () => void
  isPending: boolean
  /** Why the server refused the merge itself. The preview catches most
   *  refusals before the click, but the rows can change under an open
   *  dialog, and a Merge button that does nothing is what swallowing this
   *  looked like. */
  error?: string | null
}

/**
 * Merge two selected rows.
 *
 * This used to ask one question — which row to keep — and answer none: it
 * showed the two rows and a badge, and left the reader to work out what the
 * merged transaction would say. With a split on one side the category read
 * as simply dropped, under a note about lines having to "add up". It shows
 * the result now (`MergePair`, the server's own preview) and asks about the
 * only things that are a choice: the fields the two rows disagree on.
 *
 * Which row survives is no longer asked. It is the server's decision
 * (`choose_survivor`) and it changes nothing a person can see — every value
 * either carries over or is picked here.
 */
export function MergePreviewModal({
  budgetId,
  transactions,
  payeeMap,
  categoryLabels,
  accountOnBudget,
  onConfirm,
  onCancel,
  isPending,
  error,
}: Props) {
  const [first, second] = transactions
  const [keep, setKeep] = useState<MergeKeep>({})
  const preview = useMergePreview(budgetId, [first.id, second.id], keep)
  const refusal = preview.isError
    ? apiErrorMessage(preview.error, 'the result could not be worked out')
    : null

  return (
    <Dialog
      title="Merge transactions"
      onClose={onCancel}
      historyKey="merge-preview"
      className="merge-modal"
      footer={
        <div className="dialog-actions">
          {error && <span className="dialog-form__error">{error}</span>}
          <div className="dialog-actions__end">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={onCancel}
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--primary"
              onClick={() => onConfirm(keep)}
              // Nothing to merge into until the server has said what the
              // result is, and nothing at all when it has said no.
              disabled={isPending || !preview.data || preview.isError}
            >
              {isPending ? 'Merging…' : 'Merge'}
            </button>
          </div>
        </div>
      }
    >
      <MergePair
        rows={transactions}
        labels={pairLabels(first, second)}
        preview={preview.isError ? undefined : preview.data}
        refusal={refusal}
        keep={keep}
        onKeepChange={setKeep}
        payeeMap={payeeMap}
        categoryLabels={categoryLabels}
        accountOnBudget={accountOnBudget}
      />
    </Dialog>
  )
}
