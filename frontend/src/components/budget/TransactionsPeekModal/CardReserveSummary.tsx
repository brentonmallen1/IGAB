import { useCardTimeline } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { addMonths } from '../../../utils/dates'
import { reserveMonth } from '../CreditCardsSection/cardRow'
import './CardReserveSummary.css'

/**
 * Under the card-reserve list: from Set aside going into the month, through
 * the rows above, to Set aside at its end.
 *
 * Every figure is served — the list's total by the listing, the rest by the
 * card's timeline (`/cards/{id}/timeline/{month}`) — and `reserveMonth`
 * chooses the lines. Nothing here adds them up; the closing figure is the
 * timeline's own, and the server pins that the rows reconcile to it.
 */
export function CardReserveSummary({
  budgetId,
  accountId,
  month,
  listedNet,
}: {
  budgetId: string
  accountId: string
  month: string
  /** The listing's `total_amount` for these rows: register-signed. */
  listedNet: number
}) {
  const { formatMoney, formatMonth } = useFormatters()
  const { data, isPending, isError } = useCardTimeline(budgetId, accountId, month)
  if (isPending) return <p className="card-reserve-summary__note">Reading the card's month…</p>
  if (isError || !data) {
    return <p className="card-reserve-summary__note">The month's figures could not be loaded.</p>
  }
  const { before, lines, after } = reserveMonth(data.months, month, listedNet)
  return (
    <dl className="card-reserve-summary" aria-label={`How ${formatMonth(month)} set money aside`}>
      <div className="card-reserve-summary__row card-reserve-summary__row--edge">
        <dt>Set aside going in, end of {formatMonth(addMonths(month, -1))}</dt>
        <dd className="tabular">{formatMoney(before)}</dd>
      </div>
      {lines.map((line) => (
        <div className="card-reserve-summary__row" key={line.label}>
          <dt>{line.label}</dt>
          <dd className="tabular">
            {line.sign} {formatMoney(line.value)}
          </dd>
        </div>
      ))}
      <div className="card-reserve-summary__row card-reserve-summary__row--total">
        <dt>Set aside at the end of {formatMonth(month)}</dt>
        <dd className="tabular">{formatMoney(after)}</dd>
      </div>
    </dl>
  )
}
