import { useFormatters } from '../../../hooks/useFormatters'
import { availableTone, figureClass, signTone } from '../../../utils/figureTone'
import type { BalanceTotals } from '../budgetTotals'

interface Props {
  totals: BalanceTotals
  /** The panels word the same figures for their own context ("Assigned This
   *  Month" / "Assigned in March"); the figures and their colours are one. */
  labels: { leftOver: string; assigned: string; activity: string }
}

/**
 * Left over + assigned + activity = available, for a set of envelopes.
 *
 * The inspector drew this block twice — the Available Balance panel and the
 * month summary — with the same four rows and their own colouring, which
 * painted Assigned green (the grid's Assigned column is plain) and left
 * positive Activity plain (the grid paints it). Both now colour as the grid
 * does, through figureTone.
 */
export function BalanceBreakdownRows({ totals, labels }: Props) {
  const { formatMoney } = useFormatters()
  return (
    <>
      <div className="inspector-breakdown__row">
        <span>{labels.leftOver}</span>
        <span className="tabular">{formatMoney(totals.carriedOver)}</span>
      </div>
      <div className="inspector-breakdown__row">
        <span>{labels.assigned}</span>
        <span className="tabular">
          {totals.assigned > 0 ? '+' : ''}
          {formatMoney(totals.assigned)}
        </span>
      </div>
      <div className="inspector-breakdown__row">
        <span>{labels.activity}</span>
        <span className={`tabular ${figureClass('flow', signTone(totals.activity))}`}>
          {formatMoney(totals.activity)}
        </span>
      </div>
      <div className="inspector-breakdown__total">
        <span>Available</span>
        <span className={`tabular ${figureClass('balance', availableTone(totals))}`}>
          {formatMoney(totals.available)}
        </span>
      </div>
    </>
  )
}
