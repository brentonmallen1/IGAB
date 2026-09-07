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

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const result = await clone.mutateAsync({
      budgetId,
      name: name.trim() || undefined,
      structure_only: structureOnly,
      as_of: structureOnly ? asOf : undefined,
    })
    onCloned?.(result.budget_id)
    onClose()
  }

  return (
    <Dialog title={`Copy “${budgetName}”`} onClose={onClose} historyKey="clone-budget">
      <form className="clone-modal" onSubmit={submit}>
        <label className="clone-modal__field">
          <span>Name</span>
          <input
            className="clone-modal__input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <span className="clone-modal__hint">
            A name already in use gets a number added rather than being refused.
          </span>
        </label>

        <fieldset className="clone-modal__choice">
          <legend>What to copy</legend>
          <label className="clone-modal__option">
            <input
              type="radio"
              name="clone-scope"
              checked={!structureOnly}
              onChange={() => setStructureOnly(false)}
            />
            <span>
              <strong>Everything</strong>
              <span className="clone-modal__hint">
                Transactions, assignments, schedules and history — a working duplicate to experiment
                in. It is not connected to your bank.
              </span>
            </span>
          </label>
          <label className="clone-modal__option">
            <input
              type="radio"
              name="clone-scope"
              checked={structureOnly}
              onChange={() => setStructureOnly(true)}
            />
            <span>
              <strong>Structure only</strong>
              <span className="clone-modal__hint">
                Accounts, categories, targets, tags, payees, filters and views — the arrangement,
                with the register emptied. Each account opens on one Starting Balance row, so the
                copy starts from the balances you actually have.
              </span>
            </span>
          </label>
        </fieldset>

        {structureOnly && (
          <label className="clone-modal__field">
            <span>Starting from</span>
            <input
              type="date"
              className="clone-modal__input"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
            <span className="clone-modal__hint">
              Balances are taken as they stood on this day; anything after it is left behind.
            </span>
          </label>
        )}

        <div className="clone-modal__actions">
          <button type="button" className="clone-modal__btn" onClick={onClose}>
            Cancel
          </button>
          <button
            type="submit"
            className="clone-modal__btn clone-modal__btn--primary"
            disabled={clone.isPending}
          >
            {clone.isPending ? 'Copying…' : 'Copy budget'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}
