import { useState } from 'react'
import { useCloneBudget } from '../../api/budgetSnapshots'
import { Dialog } from '../common/Dialog/Dialog'
import { today } from '../../utils/dates'
import './CloneBudgetModal.css'

interface Props {
  budgetId: string
  budgetName: string
  onClose: () => void
  onCloned?: (newBudgetId: string) => void
}

/**
 * Copy a budget, whole or as a fresh start.
 *
 * The choice is what to do with the past, and it is the only choice here:
 * everything else about a copy — new ids, no bank link, the same
 * arrangement — is what a copy always is. A structure-only copy keeps each
 * account's position through one Starting Balance row, so a fresh start
 * opens on the balances you have rather than on zero.
 */
export function CloneBudgetModal({ budgetId, budgetName, onClose, onCloned }: Props) {
  const clone = useCloneBudget()
  const [name, setName] = useState(`${budgetName} copy`)
  const [structureOnly, setStructureOnly] = useState(false)
  const [asOf, setAsOf] = useState(today())
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (structureOnly && !asOf) {
      setError('Pick the day the copy starts from')
      return
    }
    setError(null)
    try {
      const result = await clone.mutateAsync({
        budgetId,
        name: name.trim() || undefined,
        structure_only: structureOnly,
        as_of: structureOnly ? asOf : undefined,
      })
      onCloned?.(result.budget_id)
      onClose()
    } catch {
      // useCloneBudget's onError has already said why, in a toast.
    }
  }

  return (
    <Dialog
      title={`Copy “${budgetName}”`}
      onClose={onClose}
      historyKey="clone-budget"
      footer={
        <div className="dialog-actions">
          {error && <span className="dialog-form__error">{error}</span>}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              form="clone-budget-form"
              className="dialog-btn dialog-btn--primary"
              disabled={clone.isPending}
            >
              {clone.isPending ? 'Copying…' : 'Copy budget'}
            </button>
          </div>
        </div>
      }
    >
      <form id="clone-budget-form" className="dialog-form" onSubmit={submit}>
        <div className="dialog-form__field">
          <label htmlFor="clone-budget-name">Name</label>
          <input
            id="clone-budget-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <p className="dialog-form__hint">
            A name already in use gets a number added rather than being refused.
          </p>
        </div>

        <fieldset className="clone-modal__choice">
          <legend className="dialog-form__field">What to copy</legend>
          <label className="dialog-form__field dialog-form__field--inline dialog-form__field--multiline">
            <input
              type="radio"
              name="clone-scope"
              checked={!structureOnly}
              onChange={() => setStructureOnly(false)}
            />
            <span className="clone-modal__option">
              <strong>Everything</strong>
              <span className="dialog-form__hint">
                Transactions, assignments, schedules and history — a working duplicate to experiment
                in. It is not connected to your bank.
              </span>
            </span>
          </label>
          <label className="dialog-form__field dialog-form__field--inline dialog-form__field--multiline">
            <input
              type="radio"
              name="clone-scope"
              checked={structureOnly}
              onChange={() => setStructureOnly(true)}
            />
            <span className="clone-modal__option">
              <strong>Structure only</strong>
              <span className="dialog-form__hint">
                Accounts, categories, targets, tags, payees, filters and views — the arrangement,
                with the register emptied. Each account opens on one Starting Balance row, so the
                copy starts from the balances you actually have.
              </span>
            </span>
          </label>
        </fieldset>

        {structureOnly && (
          <div className="dialog-form__field">
            <label htmlFor="clone-budget-as-of">Starting from</label>
            <input
              id="clone-budget-as-of"
              type="date"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
            <p className="dialog-form__hint">
              Balances are taken as they stood on this day; anything after it is left behind.
            </p>
          </div>
        )}
      </form>
    </Dialog>
  )
}
