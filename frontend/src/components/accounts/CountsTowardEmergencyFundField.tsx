import {
  COUNTS_TOWARD_EMERGENCY_FUND_HELP,
  COUNTS_TOWARD_EMERGENCY_FUND_NEEDS_SAVINGS,
} from '../../constants/accountTypes'
import { isTrackedAsset } from '../../utils/accountKinds'

interface Props {
  onBudget: boolean
  classification: 'asset' | 'liability' | null | undefined
  countsAsSavings: boolean
  checked: boolean
  onChange: (checked: boolean) => void
}

/** The "Counts toward emergency fund" toggle, for the account modals. Offered
 *  where Counts as savings is (an off-budget asset — `isTrackedAsset`), and
 *  disabled until that is on: the server refuses the flag without it
 *  (`canCountTowardEmergencyFund`). The modal clears the choice when Counts as
 *  savings goes off, so turning it back on does not quietly restore it. */
export function CountsTowardEmergencyFundField({
  onBudget,
  classification,
  countsAsSavings,
  checked,
  onChange,
}: Props) {
  if (!isTrackedAsset({ on_budget: onBudget, classification: classification ?? null })) {
    return null
  }
  // The hint sits outside the label, as Counts as savings' does, so the
  // checkbox's accessible name stays "Counts toward emergency fund".
  return (
    <div className="dialog-form__field">
      <label className="dialog-form__field dialog-form__field--inline">
        <input
          type="checkbox"
          checked={countsAsSavings && checked}
          disabled={!countsAsSavings}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>Counts toward emergency fund</span>
      </label>
      <p className="dialog-form__hint">
        {countsAsSavings
          ? COUNTS_TOWARD_EMERGENCY_FUND_HELP
          : COUNTS_TOWARD_EMERGENCY_FUND_NEEDS_SAVINGS}
      </p>
    </div>
  )
}
