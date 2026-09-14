import { useId } from 'react'
import toast from 'react-hot-toast'
import { useReportSettings, useSetReportSettings } from '../../../api/reports'
import { apiErrorMessage } from '../../../api/client'
import './SpreadSinkingFundsToggle.css'

interface Props {
  budgetId: string | null
}

/**
 * The budget's "spread yearly bills" setting, where the essentials figure is
 * read: the Essentials report, the Emergency Fund report and the Guide's
 * sizer. One setting for the whole budget (`services/report_settings.py`) —
 * flipping it here moves the Overview card and the Guide's targets too, so
 * the mutation stales all of them, and the change undoes like any other.
 *
 * A native checkbox, so Space toggles it and the label is its accessible
 * name; the hint is linked by `aria-describedby` rather than put inside the
 * label, where it would become part of the name.
 */
export function SpreadSinkingFundsToggle({ budgetId }: Props) {
  const id = useId()
  const hintId = `${id}-hint`
  const { data } = useReportSettings(budgetId)
  const setSettings = useSetReportSettings(budgetId)
  const checked = data?.spread_sinking_funds ?? true

  return (
    <div className="spread-toggle">
      <label className="spread-toggle__label" htmlFor={id}>
        <input
          id={id}
          type="checkbox"
          className="spread-toggle__input"
          checked={checked}
          disabled={!data || setSettings.isPending}
          aria-describedby={hintId}
          onChange={(e) =>
            setSettings.mutate(
              { spread_sinking_funds: e.target.checked },
              { onError: (err) => toast.error(apiErrorMessage(err, 'Could not save the setting')) }
            )
          }
        />
        <span>Spread yearly bills over 12 months</span>
      </label>
      <p id={hintId} className="spread-toggle__hint">
        Bills in Long-term expense categories count as a twelfth a month in essentials, targets and
        runway. Charts of what you spent stay as paid.
      </p>
    </div>
  )
}
