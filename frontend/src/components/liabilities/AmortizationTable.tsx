import { useState } from 'react'
import type { AmortizationMonth } from '../../api/liabilities'
import { formatMoney } from '../../utils/money'
import { formatMonthYear } from './PayoffPill'
import './AmortizationTable.css'

const PAGE = 24

interface Props {
  schedule: AmortizationMonth[]
}

export function AmortizationTable({ schedule }: Props) {
  const [visible, setVisible] = useState(PAGE)
  const rows = schedule.slice(0, visible)

  if (schedule.length === 0) {
    return <div className="amort-table__empty">No schedule — this liability is paid off.</div>
  }

  return (
    <div className="amort-table">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Month</th>
            <th className="amort-table__num">Payment</th>
            <th className="amort-table__num">Principal</th>
            <th className="amort-table__num">Interest</th>
            <th className="amort-table__num">Balance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.month_index}>
              <td data-label="#">{m.month_index}</td>
              <td data-label="Month">{formatMonthYear(m.date)}</td>
              <td data-label="Payment" className="amort-table__num">
                {formatMoney(Number(m.payment))}
              </td>
              <td data-label="Principal" className="amort-table__num">
                {formatMoney(Number(m.principal_paid))}
              </td>
              <td data-label="Interest" className="amort-table__num amort-table__interest">
                {formatMoney(Number(m.interest_paid))}
              </td>
              <td data-label="Balance" className="amort-table__num">
                {formatMoney(Number(m.balance))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {visible < schedule.length && (
        <button className="amort-table__more" onClick={() => setVisible((v) => v + PAGE)}>
          Show more months ({schedule.length - visible} remaining)
        </button>
      )}
    </div>
  )
}
