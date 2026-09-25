import { useFormatters } from '../../../hooks/useFormatters'
import { addMonths } from '../../../utils/dates'
import { Dialog } from '../../common/Dialog/Dialog'
import type { OverspentLastMonth } from '../budgetTotals'
import './LastMonthModal.css'

interface Props {
  /** The month being viewed; the overspending was the month before it. */
  month: string
  lastMonth: OverspentLastMonth
  onClose: () => void
}

/**
 * What the 1st took out of Ready to Assign, envelope by envelope.
 *
 * The header only carries the total, as a pill: the list sat there as a
 * sentence once and wrapped into two ragged lines beside the number. Every
 * figure is served (`overspent_last_month`); this names and lists them.
 */
export function LastMonthModal({ month, lastMonth, onClose }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  const previous = formatMonth(addMonths(month, -1))
  return (
    <Dialog
      title={`Overspent in ${previous}`}
      onClose={onClose}
      historyKey="overspent-last-month"
      className="last-month"
      footer={
        <div className="dialog-actions">
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      }
    >
      <p className="last-month__lede">
        These ended {previous} below zero, so this month&rsquo;s Ready to Assign covered them on the
        1st. Nothing to do now.
      </p>
      <dl className="last-month__list">
        {lastMonth.sources.map((s) => (
          <div className="last-month__row" key={s.name}>
            <dt>{s.name}</dt>
            <dd className="tabular">{formatMoney(-s.amount)}</dd>
          </div>
        ))}
        <div className="last-month__row last-month__row--total">
          <dt>Total</dt>
          <dd className="tabular">{formatMoney(-lastMonth.total)}</dd>
        </div>
      </dl>
    </Dialog>
  )
}
