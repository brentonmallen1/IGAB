import { useFormatters } from '../../hooks/useFormatters'
import './DrillDownTable.css'

export interface DrillDownRow {
  id: string
  name: string
  subName?: string
  amount: number
  pct?: number
  extra?: string
}

interface Props {
  rows: DrillDownRow[]
  total?: number
  onRowClick?: (row: DrillDownRow) => void
  amountLabel?: string
}

export function DrillDownTable({ rows, total, onRowClick, amountLabel = 'Amount' }: Props) {
  const { formatMoney } = useFormatters()
  if (rows.length === 0) return null

  return (
    <div className="ddt">
      <table className="ddt__table">
        <caption className="sr-only">Breakdown by name</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            {rows.some((r) => r.subName) && <th scope="col">Group</th>}
            <th scope="col" className="ddt__num">{amountLabel}</th>
            {rows.some((r) => r.pct !== undefined) && <th scope="col" className="ddt__num">%</th>}
            {rows.some((r) => r.extra) && <th scope="col" className="ddt__num">Extra</th>}
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
              <td className="ddt__num">{formatMoney(Math.abs(row.amount))}</td>
              {rows.some((r) => r.pct !== undefined) && (
                <td className="ddt__num ddt__muted">{row.pct?.toFixed(1) ?? ''}%</td>
              )}
              {rows.some((r) => r.extra) && (
                <td className="ddt__num ddt__muted">{row.extra ?? ''}</td>
              )}
            </tr>
          ))}
          {total !== undefined && (
            <tr className="ddt__total">
              <td colSpan={rows.some((r) => r.subName) ? 2 : 1}>Total</td>
              <td className="ddt__num">{formatMoney(Math.abs(total))}</td>
              {rows.some((r) => r.pct !== undefined) && <td />}
              {rows.some((r) => r.extra) && <td />}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
