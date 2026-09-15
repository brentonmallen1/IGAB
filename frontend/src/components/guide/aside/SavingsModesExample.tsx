import { useState } from 'react'
import { useMoneyMonth } from '../../../api/moneyRules'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'
import type { SavingsMode } from '../../../types'
import { SAVINGS_MODE_OPTIONS, savingsModeLabel } from '../../../utils/savingsModes'
import { signedMoney } from '../money/moveAnswer'
import { GENERAL_SAVINGS_MONTH, GENERAL_SAVINGS_REQUESTS } from './asideExampleMoves'
import { envelopeLeft } from './savingsMonth'
import './SavingsModesExample.css'

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

/** Zero reads as "nothing", not "−$0.00". */
function savedText(value: number, formatMoney: (n: number) => string) {
  return value === 0 ? formatMoney(0) : signedMoney(value, formatMoney)
}

/** One month in General Savings, counted either way — rows and total served. */
export function SavingsModesExample() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [mode, setMode] = useState<SavingsMode>('sent_out')
  const { data, isError } = useMoneyMonth(budgetId, GENERAL_SAVINGS_REQUESTS[mode])
  const { formatMoney } = useFormatters()
  const moves = GENERAL_SAVINGS_MONTH[mode]

  return (
    <div className="savings-modes-example surface surface--raised">
      <fieldset className="savings-modes-example__switch">
        <legend className="savings-modes-example__legend">Counts as saved</legend>
        {SAVINGS_MODE_OPTIONS.map((option) => (
          <label
            key={option.mode}
            htmlFor={`savings-modes-example-${option.mode}`}
            className={`savings-modes-example__option ${
              option.mode === mode ? 'savings-modes-example__option--on' : ''
            }`}
          >
            <input
              type="radio"
              id={`savings-modes-example-${option.mode}`}
              name="savings-modes-example"
              value={option.mode}
              checked={option.mode === mode}
              onChange={() => setMode(option.mode)}
            />
            {sentence(option.short)}
          </label>
        ))}
      </fieldset>

      {isError ? (
        <p className="savings-modes-example__status">The example could not be loaded.</p>
      ) : !data ? (
        <p className="savings-modes-example__status">Working it out…</p>
      ) : (
        <>
          <div className="savings-modes-example__scroll">
            <table
              className="savings-modes-example__table"
              aria-label={`One month in General Savings, counted as saved ${savingsModeLabel(mode)}`}
            >
              <thead>
                <tr>
                  <th scope="col">What happened</th>
                  <th scope="col" className="savings-modes-example__num">
                    Counts as saved
                  </th>
                  <th scope="col">Why</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={row.label}>
                    <th scope="row">
                      {row.label}
                      <span className="savings-modes-example__amount">
                        {formatMoney(moves[i].move.amount)}
                      </span>
                    </th>
                    <td className="savings-modes-example__num">
                      {savedText(row.explanation.figures.savings, formatMoney)}
                    </td>
                    <td className="savings-modes-example__why">{moves[i].why[mode]}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">Saved this month</th>
                  <td className="savings-modes-example__num">
                    {savedText(data.figures.savings, formatMoney)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="savings-modes-example__note">
            Either way, {formatMoney(envelopeLeft(data))} is still in the envelope.
          </p>
        </>
      )}
    </div>
  )
}
