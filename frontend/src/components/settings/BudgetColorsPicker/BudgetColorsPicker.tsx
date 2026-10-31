import { useFormatters } from '../../../hooks/useFormatters'
import {
  BUDGET_COLOR_MODES,
  BUDGET_COLOR_MODE_COPY,
  availableTone,
  figureClass,
  signTone,
  type BudgetColorMode,
} from '../../../utils/figureTone'
import './BudgetColorsPicker.css'

/** The sample: an envelope with money left, one overspent in cash, one whose
 *  red rode on a card, and a refund — the four readings a figure can have. */
const SAMPLE = [
  { name: 'Food', activity: -42, available: 58, credit_overspent: 0 },
  { name: 'Dining', activity: -62, available: -12, credit_overspent: 0 },
  { name: 'Fuel', activity: -30, available: -30, credit_overspent: 30 },
  { name: 'Home', activity: 20, available: 0, credit_overspent: 0 },
]
const SAMPLE_READY_TO_ASSIGN = 120

interface Props {
  value: BudgetColorMode
  onChange: (mode: BudgetColorMode) => void
}

/**
 * The budget colour setting, as three cards that are each their own preview.
 *
 * Each card carries `data-budget-colors` for its own mode, so its figures
 * render as that mode will, whichever one the app is set to — the variables
 * in base.css ("Budget figures") resolve from the nearest attribute. The
 * tones come from figureTone, the same calls the grid makes, so the sample
 * cannot colour a figure differently from the budget it stands for.
 */
export function BudgetColorsPicker({ value, onChange }: Props) {
  const { formatMoney } = useFormatters()
  return (
    <fieldset className="budget-colors">
      <legend className="sr-only">Budget colours</legend>
      {BUDGET_COLOR_MODES.map((mode) => (
        <label key={mode} className="budget-colors__card" data-budget-colors={mode}>
          <span className="budget-colors__head">
            <input
              type="radio"
              name="budget-colors"
              value={mode}
              checked={value === mode}
              onChange={() => onChange(mode)}
            />
            <span className="budget-colors__label">{BUDGET_COLOR_MODE_COPY[mode].label}</span>
          </span>
          <span className="budget-colors__desc">{BUDGET_COLOR_MODE_COPY[mode].desc}</span>
          <span className="budget-colors__sample" aria-hidden="true">
            <span className="budget-colors__tba">
              Ready to Assign
              <span
                className={`tabular ${figureClass('balance', signTone(SAMPLE_READY_TO_ASSIGN))}`}
              >
                {formatMoney(SAMPLE_READY_TO_ASSIGN)}
              </span>
            </span>
            <span className="budget-colors__row budget-colors__row--head">
              <span />
              <span>Activity</span>
              <span>Available</span>
            </span>
            {SAMPLE.map((row) => {
              const tone = availableTone(row)
              return (
                <span
                  key={row.name}
                  className={`budget-colors__row${tone === 'negative' ? ' budget-colors__row--overspent' : ''}`}
                >
                  <span className="budget-colors__name">{row.name}</span>
                  <span className={`tabular ${figureClass('flow', signTone(row.activity))}`}>
                    {formatMoney(row.activity)}
                  </span>
                  <span className={`tabular ${figureClass('balance', tone)}`}>
                    {formatMoney(row.available)}
                  </span>
                </span>
              )
            })}
          </span>
        </label>
      ))}
    </fieldset>
  )
}
