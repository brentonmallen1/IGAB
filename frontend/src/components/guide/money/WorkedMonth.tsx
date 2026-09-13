import { useMoneyMonth, type MoneyMonthResponse } from '../../../api/moneyRules'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'
import { pct } from '../../reports/charts/savingsRateView'
import { ClassChip } from './ClassChip'
import { WORKED_MONTH } from './workedMonthMoves'
import './WorkedMonth.css'

type Row = MoneyMonthResponse['rows'][number]

/** The legs a report sees: the on-budget ones, or the tracked side when the
 * whole move happened off budget. */
function shownLegs(row: Row) {
  const onBudget = row.explanation.legs.filter((l) => l.on_budget)
  return onBudget.length > 0 ? onBudget : row.explanation.legs
}

/** One invented month, every figure served by the classifier. */
export function WorkedMonth() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data, isError } = useMoneyMonth(budgetId, WORKED_MONTH)
  const { formatMoney } = useFormatters()

  if (isError) return <p className="worked-month__status">The worked month could not be loaded.</p>
  if (!data) return <p className="worked-month__status">Working it out…</p>

  const { figures } = data
  return (
    <div className="worked-month">
      <div className="worked-month__scroll surface surface--raised">
        <table className="worked-month__table" aria-label="The worked month">
          <thead>
            <tr>
              <th scope="col">Move</th>
              <th scope="col" className="worked-month__num">
                Amount
              </th>
              <th scope="col">Counts as</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => {
              const legs = shownLegs(row)
              const offBudget = legs.every((l) => !l.on_budget)
              const classes = [...new Map(legs.map((l) => [l.cls, l])).values()]
              return (
                <tr key={row.label}>
                  <th scope="row">{row.label}</th>
                  <td className="worked-month__num">{formatMoney(WORKED_MONTH[i].amount)}</td>
                  <td>
                    <span className="worked-month__classes">
                      {classes.map((l) => (
                        <ClassChip key={l.cls} cls={l.cls} label={l.class_label} />
                      ))}
                      {offBudget && (
                        <span className="worked-month__note">off budget, not counted</span>
                      )}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <dl className="worked-month__totals">
        <Figure label="Income" value={formatMoney(figures.income)} />
        <Figure label="Spending" value={formatMoney(figures.spending)} />
        <Figure label="Saved" value={formatMoney(figures.savings)} />
        <Figure label="Debt principal" value={formatMoney(figures.debt_principal)} />
        <Figure label="Savings rate" value={pct(figures.savings_rate)} emphasis />
        <Figure
          label="Savings rate with debt"
          value={pct(figures.savings_rate_with_debt)}
          emphasis
        />
      </dl>
    </div>
  )
}

function Figure({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className={`worked-month__figure ${emphasis ? 'worked-month__figure--rate' : ''}`}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
