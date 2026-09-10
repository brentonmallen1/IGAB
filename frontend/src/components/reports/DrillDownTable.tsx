import { useFormatters } from '../../hooks/useFormatters'
import { drillDownFooter, type WiderSet } from './drillDownTotals'
import './DrillDownTable.css'

export interface DrillDownRow {
  id: string
  name: string
  subName?: string
  /** Signed, in the direction `amountLabel` names: positive means "spent"
   *  under a Spent column, negative the other way.
   *
   *  This used to render through `Math.abs`, so every caller negated its
   *  figure on the way in for a sign the table then discarded — and a month
   *  whose refunds beat its spending drew "we spent $40" for "we got $40
   *  back". */
  amount: number
  pct?: number
  extra?: string
}

interface Props {
  rows: DrillDownRow[]
  /** The set `rows` was sliced from, when the rows are only part of it.
   *
   *  Drawn beside the total, never as it — see `drillDownTotals.ts` for what
   *  went wrong when a wider figure was passed as the rows' own total. */
  wider?: WiderSet
  onRowClick?: (row: DrillDownRow) => void
  amountLabel?: string
}

export function DrillDownTable({ rows, wider, onRowClick, amountLabel = 'Amount' }: Props) {
  const { formatMoney } = useFormatters()
  if (rows.length === 0) return null

  // Always the sum of the rows above it.
  const footer = drillDownFooter(rows, wider, formatMoney)

  return (
    <div className="ddt">
      <table className="ddt__table">
        <caption className="sr-only">Breakdown by name</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            {rows.some((r) => r.subName) && <th scope="col">Group</th>}
            <th scope="col" className="ddt__num">
              {amountLabel}
            </th>
            {rows.some((r) => r.pct !== undefined) && (
              <th scope="col" className="ddt__num">
                %
              </th>
            )}
            {rows.some((r) => r.extra) && (
              <th scope="col" className="ddt__num">
                Extra
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={onRowClick ? 'ddt__row--clickable' : ''}
              onClick={() => onRowClick?.(row)}
            >
              <td className="ddt__name">{row.name}</td>
              {rows.some((r) => r.subName) && <td className="ddt__sub">{row.subName ?? ''}</td>}
              <td className="ddt__num">{formatMoney(row.amount)}</td>
              {rows.some((r) => r.pct !== undefined) && (
                <td className="ddt__num ddt__muted">{row.pct?.toFixed(1) ?? ''}%</td>
              )}
              {rows.some((r) => r.extra) && (
                <td className="ddt__num ddt__muted">{row.extra ?? ''}</td>
              )}
            </tr>
          ))}
          <tr className="ddt__total">
            <td colSpan={rows.some((r) => r.subName) ? 2 : 1}>
              {footer.wider === null ? 'Total' : `Total of the ${rows.length} shown`}
            </td>
            <td className="ddt__num">{formatMoney(footer.shown)}</td>
            {rows.some((r) => r.pct !== undefined) && <td />}
            {rows.some((r) => r.extra) && <td />}
          </tr>
          {footer.wider !== null && (
            <tr className="ddt__of">
              <td colSpan={rows.some((r) => r.subName) ? 2 : 1}>{footer.widerLabel}</td>
              <td className="ddt__num">{formatMoney(footer.wider)}</td>
              {rows.some((r) => r.pct !== undefined) && (
                <td className="ddt__num ddt__muted">
                  {footer.share === null ? '' : `${footer.share.toFixed(1)}%`}
                </td>
              )}
              {rows.some((r) => r.extra) && <td />}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
