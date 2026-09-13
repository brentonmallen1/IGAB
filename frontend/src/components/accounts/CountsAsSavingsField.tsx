import { COUNTS_AS_SAVINGS_HELP } from '../../constants/accountTypes'
import { isTrackedAsset } from '../../utils/accountKinds'
import './AccountSettingsModal.css'

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
  return (
    <div className="acct-modal__field">
      <div className="acct-modal__field--row acct-modal__field">
        <label className="acct-modal__label" htmlFor="acct-counts-as-savings">
          Counts as savings
        </label>
        <input
          id="acct-counts-as-savings"
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
      </div>
      <p className="acct-modal__hint">{COUNTS_AS_SAVINGS_HELP}</p>
    </div>
  )
}
