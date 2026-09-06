import { Calculator } from 'lucide-react'
import './PaydownWhatIf.css'

export interface WhatIfSavings {
  /** Null when the contractual baseline never pays off — there is no
   *  "sooner" to measure against something that never happens. */
  monthsSooner: number | null
  interestSaved: number
}

interface Props {
  /** The extra-per-month field's value: the stored plan until touched. */
  extra: string
  onExtraChange: (value: string) => void
  /** The one-off-to-principal field's value. */
  curtailment: string
  onCurtailmentChange: (value: string) => void
  /** Parsed and debounced — what the schedule below was actually built from. */
  extraPayment: number
  curtailmentAmount: number
  /** The saved plan, if any, so the buttons can say which state this is. */
  storedPlan: number | null
  savings: WhatIfSavings | null
  onSavePlan: () => void
  onClearPlan: () => void
  saving: boolean
  formatMoney: (n: number) => string
  /** Terms are missing, so there is nothing to project — the fields would
   *  accept a number and change nothing. */
  disabled?: boolean
}

/**
 * "What if I paid more?", asked in one place with its answer under it.
 *
 * Every figure this panel produces was already being computed and drawn — the
 * accelerated curve on the chart, the alternate column in the schedule, the
 * saved plan. What did not exist was anywhere to *find* it: the two inputs
 * were unlabelled-looking number boxes wedged into the chart's header beside
 * the Now/Beginning toggle, they said nothing until you had already typed in
 * them, and neither used the word people search for. The report that produced
 * this panel was "I thought we had added mechanisms for curtailment payments
 * but I didn't see a place to handle that" — from someone who had shipped the
 * feature.
 *
 * So: a heading that asks the question, fields that say what they do, the
 * word *curtailment* written down, and a worked example sitting in the empty
 * state so the panel is useful before anything is typed.
 *
 * The arithmetic is the server's (`/liabilities/{id}/amortization` with
 * `extra_payment` and `curtailment`); nothing is computed here.
 */
export function PaydownWhatIf({
  extra,
  onExtraChange,
  curtailment,
  onCurtailmentChange,
  extraPayment,
  curtailmentAmount,
  storedPlan,
  savings,
  onSavePlan,
  onClearPlan,
  saving,
  formatMoney,
  disabled = false,
}: Props) {
  const asked = extraPayment > 0 || curtailmentAmount > 0
  const isSavedPlan = storedPlan !== null && extraPayment === storedPlan && curtailmentAmount === 0

  return (
    <div className="paydown-whatif">
      <div className="paydown-whatif__head">
        <Calculator size={14} aria-hidden />
        <h3 className="paydown-whatif__title">What if you paid more?</h3>
      </div>

      <div className="paydown-whatif__fields">
        <label className="paydown-whatif__field">
          <span className="paydown-whatif__label">Extra every month</span>
          <input
            type="number"
            min="0"
            step="10"
            inputMode="decimal"
            placeholder="0"
            value={extra}
            onChange={(e) => onExtraChange(e.target.value)}
            disabled={disabled}
          />
          <span className="paydown-whatif__hint">
            On top of the minimum, every month, straight to principal.
          </span>
        </label>
        <label className="paydown-whatif__field">
          <span className="paydown-whatif__label">A one-off payment (curtailment)</span>
          <input
            type="number"
            min="0"
            step="100"
            inputMode="decimal"
            placeholder="0"
            value={curtailment}
            onChange={(e) => onCurtailmentChange(e.target.value)}
            disabled={disabled}
          />
          <span className="paydown-whatif__hint">
            A single lump sum against the balance today — a mortgage curtailment. Interest is
            charged on the balance, so every cent of it is principal.
          </span>
        </label>
      </div>

      {disabled ? (
        <p className="paydown-whatif__empty">
          Add this liability&apos;s APR and minimum payment and these will project.
        </p>
      ) : savings ? (
        <div className="paydown-whatif__result">
          <span className="paydown-whatif__result-ask">
            {[
              extraPayment > 0 ? `+${formatMoney(extraPayment)}/mo` : null,
              curtailmentAmount > 0 ? `${formatMoney(curtailmentAmount)} once` : null,
            ]
              .filter(Boolean)
              .join(' and ')}
          </span>
          <span className="paydown-whatif__result-gain">
            {savings.monthsSooner !== null
              ? `paid off ${savings.monthsSooner} month${savings.monthsSooner === 1 ? '' : 's'} sooner`
              : 'actually pays off'}
            {' · '}
            {formatMoney(savings.interestSaved)} less interest
          </span>
          {extraPayment > 0 && !isSavedPlan && (
            <button
              type="button"
              className="paydown-whatif__plan-btn"
              onClick={onSavePlan}
              disabled={saving}
            >
              Save as my plan
            </button>
          )}
          {isSavedPlan && (
            <span className="paydown-whatif__plan-note">
              This is your plan
              <button
                type="button"
                className="paydown-whatif__plan-btn"
                onClick={onClearPlan}
                disabled={saving}
              >
                Clear
              </button>
            </span>
          )}
        </div>
      ) : asked ? (
        // Something was typed and no comparison came back: the accelerated
        // path still never clears, so there is no saving to report.
        <p className="paydown-whatif__empty">
          Even at that pace this does not clear — the payment is not covering the interest.
        </p>
      ) : (
        <p className="paydown-whatif__empty">
          Type a figure and the chart, the schedule and the payoff date below all answer for it.
          Nothing is saved until you say so.
        </p>
      )}
    </div>
  )
}
