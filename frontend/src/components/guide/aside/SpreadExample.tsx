import { Link } from 'react-router-dom'
import { useSpreadExample } from '../../../api/guide'
import { useFormatters } from '../../../hooks/useFormatters'
import { useAppStore } from '../../../stores/appStore'
import { systemTagName } from '../../settings/TagsPanel/systemTagHelp'
import './SpreadExample.css'

const SINKING_TAG = systemTagName('long_term_expense')

/** A yearly bill as paid and spread — every figure served. */
export function SpreadExample() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data, isError } = useSpreadExample(budgetId)
  const { formatMoney } = useFormatters()
  const perMonth = (n: number) => `${formatMoney(n)} / mo`

  return (
    <div className="spread-example">
      <p className="guide-article__lede">
        A sinking fund is money set aside monthly for a bill that arrives all at once. The money is
        already spoken for, so it never counts as savings or emergency money, and the bill still
        counts as spending when you pay it. Your monthly essentials figure averages the last 90
        days, so a once-a-year bill distorts it: the quarter you pay it, your emergency fund goal
        jumps, and later the bill drops out entirely. Spread counts a twelfth of each {SINKING_TAG}{' '}
        bill every month instead.
      </p>

      {isError ? (
        <p className="guide-article__status">The example could not be loaded.</p>
      ) : !data ? (
        <p className="guide-article__status">Working it out…</p>
      ) : (
        <div className="guide-article__cards" aria-label="Spread example">
          <section className="surface surface--raised guide-article__card spread-example__card">
            <h4 className="spread-example__label">As paid</h4>
            <p className="spread-example__figure">{perMonth(data.as_paid_after_bill)}</p>
            <p className="spread-example__detail">
              In the three months after a yearly bill, then back to{' '}
              <strong>{formatMoney(data.as_paid_otherwise)}</strong>. The {data.goal_months}-month
              fund goal swings between <strong>{formatMoney(data.goal_as_paid_after_bill)}</strong>{' '}
              and <strong>{formatMoney(data.goal_as_paid_otherwise)}</strong>.
            </p>
          </section>
          <section className="surface surface--raised guide-article__card spread-example__card">
            <h4 className="spread-example__label">Spread (the default)</h4>
            <p className="spread-example__figure">{perMonth(data.spread)}</p>
            <p className="spread-example__detail">
              Every month, <strong>{formatMoney(data.bill_monthly_share)}</strong> of it the bill.
              The {data.goal_months}-month fund goal holds at{' '}
              <strong>{formatMoney(data.goal_spread)}</strong>.
            </p>
          </section>
        </div>
      )}

      <div className="guide-article__prose">
        <ul>
          <li>
            One setting for the whole budget, switched from the Essentials report, the Emergency
            Fund report or the sizer. The Guide, the Overview and both reports always agree.
          </li>
          <li>Each screen shows the other figure as well, so both are always in view.</li>
          <li>Charts of what you actually spent still show the bill in the month you paid it.</li>
          <li>A budget less than a year old reads low until it has seen each yearly bill once.</li>
        </ul>
      </div>
      <p className="guide-article__links">
        <Link to="/reports?tab=essentials" className="guide-article__link">
          Open the Essentials report
        </Link>
      </p>
    </div>
  )
}
