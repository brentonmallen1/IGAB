import { useState } from 'react'
import { Dialog } from '../common/Dialog/Dialog'
import { LOOKBACK_CHOICES, type DuplicateScanScope } from './duplicateScan'

interface Props {
  accountName: string
  /** The last scope used — the dialog opens on it. */
  initial: DuplicateScanScope
  onScan: (scope: DuplicateScanScope) => void
  onClose: () => void
  isPending: boolean
}

/**
 * What to look through before looking. See `duplicateScan.ts` for why the
 * scan asks at all.
 */
export function FindDuplicatesDialog({ accountName, initial, onScan, onClose, isPending }: Props) {
  const [lookbackDays, setLookbackDays] = useState(initial.lookbackDays)
  const [includeReconciled, setIncludeReconciled] = useState(initial.includeReconciled)

  return (
    <Dialog
      title="Find possible duplicates"
      onClose={onClose}
      historyKey="find-duplicates"
      footer={
        <div className="dialog-actions">
          <div className="dialog-actions__end">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              form="find-duplicates-form"
              className="dialog-btn dialog-btn--primary"
              disabled={isPending}
            >
              {isPending ? 'Looking…' : 'Find'}
            </button>
          </div>
        </div>
      }
    >
      <form
        id="find-duplicates-form"
        className="dialog-form"
        onSubmit={(e) => {
          e.preventDefault()
          onScan({ lookbackDays, includeReconciled })
        }}
      >
        <p className="dialog-form__hint">
          Looks in {accountName} for pairs with the same amount a few days apart, and lists them for
          you to merge or keep separate. Pairs you have already answered are not asked again.
        </p>
        <div className="dialog-form__field">
          <label htmlFor="find-duplicates-lookback">How far back</label>
          <select
            id="find-duplicates-lookback"
            value={lookbackDays === null ? 'all' : String(lookbackDays)}
            onChange={(e) =>
              setLookbackDays(e.target.value === 'all' ? null : Number(e.target.value))
            }
          >
            {LOOKBACK_CHOICES.map((c) => (
              <option key={c.label} value={c.days === null ? 'all' : String(c.days)}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <label className="dialog-form__field dialog-form__field--inline">
          <input
            type="checkbox"
            checked={includeReconciled}
            onChange={(e) => setIncludeReconciled(e.target.checked)}
          />
          <span>Include reconciled transactions</span>
        </label>
        <p className="dialog-form__hint">
          {includeReconciled
            ? 'A reconciled transaction is only ever paired with one that is not — two reconciled ones cannot be merged.'
            : 'Reconciled transactions are left out: your statement already agreed with them.'}
        </p>
      </form>
    </Dialog>
  )
}
