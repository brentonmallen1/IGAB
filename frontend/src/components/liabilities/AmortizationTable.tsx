import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { AmortizationMonth } from '../../api/liabilities'
import { useFormatters } from '../../hooks/useFormatters'
import { groupByYear, scheduleTotals } from './amortizationView'
import './AmortizationTable.css'

interface Props {
  schedule: AmortizationMonth[]
}

/**
 * The schedule, one row per calendar year, months on request.
 *
 * This was a flat month list paged 24 rows at a time — a 30-year mortgage
 * sat behind fifteen clicks of "show more", and the far end (where the
 * interest column finally goes quiet) was the part nobody ever reached. A
 * year row carries the sums that matter at that altitude; opening it shows
 * the months. The first year opens by default: the immediate future is the
 * part being acted on.
 *
 * The footer restates the engine's own pinned invariant where the reader
 * can check it: whenever a schedule pays off, the principal column sums to
 * the starting balance exactly.
 */
export function AmortizationTable({ schedule }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  const years = groupByYear(schedule)
  const totals = scheduleTotals(schedule)
  const [open, setOpen] = useState<ReadonlySet<number>>(
    () => new Set(years.length > 0 ? [years[0].year] : [])
  )

  if (schedule.length === 0) {
    return <div className="amort-table__empty">No schedule — this liability is paid off.</div>
  }

  function toggle(year: number) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(year)) next.delete(year)
      else next.add(year)
      return next
    })
  }

  return (
    <div className="amort-table">
      <table>
        <caption className="sr-only">Amortization schedule, grouped by year</caption>
        <thead>
          <tr>
            <th scope="col">Year</th>
            <th scope="col" className="amort-table__num">
              Payments
            </th>
            <th scope="col" className="amort-table__num">
              Principal
            </th>
            <th scope="col" className="amort-table__num">
              Interest
            </th>
            <th scope="col" className="amort-table__num">
              Balance
            </th>
          </tr>
        </thead>
        {years.map((y) => {
          const isOpen = open.has(y.year)
          return (
            <tbody key={y.year}>
              <tr
                className="amort-table__year"
                onClick={() => toggle(y.year)}
                aria-expanded={isOpen}
              >
                <td data-label="Year">
                  <span className="amort-table__year-label">
                    {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    {y.year}
                    <span className="amort-table__year-months">
                      {y.months.length} payment{y.months.length === 1 ? '' : 's'}
                    </span>
                  </span>
                </td>
                <td data-label="Payments" className="amort-table__num">
                  {formatMoney(y.payments)}
                </td>
                <td data-label="Principal" className="amort-table__num">
                  {formatMoney(y.principal)}
                </td>
                <td data-label="Interest" className="amort-table__num amort-table__interest">
                  {formatMoney(y.interest)}
                </td>
                <td data-label="Balance" className="amort-table__num">
                  {formatMoney(y.endBalance)}
                </td>
              </tr>
              {isOpen &&
                y.months.map((m) => (
                  <tr key={m.month_index} className="amort-table__month">
                    <td data-label="Month" className="amort-table__month-name">
                      {formatMonth(m.date)}
                      <span className="amort-table__month-index">#{m.month_index}</span>
                    </td>
                    <td data-label="Payment" className="amort-table__num">
                      {formatMoney(m.payment)}
                    </td>
                    <td data-label="Principal" className="amort-table__num">
                      {formatMoney(m.principal_paid)}
                    </td>
                    <td data-label="Interest" className="amort-table__num amort-table__interest">
                      {formatMoney(m.interest_paid)}
                    </td>
                    <td data-label="Balance" className="amort-table__num">
                      {formatMoney(m.balance)}
                    </td>
                  </tr>
                ))}
            </tbody>
          )
        })}
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            <td data-label="Payments" className="amort-table__num">
              {formatMoney(totals.payments)}
            </td>
            <td data-label="Principal" className="amort-table__num">
              {formatMoney(totals.principal)}
            </td>
            <td data-label="Interest" className="amort-table__num amort-table__interest">
              {formatMoney(totals.interest)}
            </td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
