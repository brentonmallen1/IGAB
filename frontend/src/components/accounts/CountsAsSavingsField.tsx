import { COUNTS_AS_SAVINGS_HELP } from '../../constants/accountTypes'
import { isTrackedAsset } from '../../utils/accountKinds'

interface Props {
  onBudget: boolean
  classification: 'asset' | 'liability' | null | undefined
  checked: boolean
  onChange: (checked: boolean) => void
}

/** The "Counts as savings" toggle, for the account modals. Renders nothing
 *  unless the account is an off-budget asset — see `isTrackedAsset`. */
export function CountsAsSavingsField({ onBudget, classification, checked, onChange }: Props) {
  if (!isTrackedAsset({ on_budget: onBudget, classification: classification ?? null })) {
    return null
  }
  // The hint sits outside the label: inside, it would join the checkbox's
  // accessible name and "Counts as savings" would stop matching it.
  return (
    <div className="dialog-form__field">
      <label className="dialog-form__field dialog-form__field--inline">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>Counts as savings</span>
      </label>
      <p className="dialog-form__hint">{COUNTS_AS_SAVINGS_HELP}</p>
    </div>
  )
}
