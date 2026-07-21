import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatMoney } from '../../utils/money'
import type { IncomeExpenseMonth } from '../../types'

interface Props {
  months: IncomeExpenseMonth[]
}

export function IncomeExpenseChart({ months }: Props) {
  if (months.length === 0) {
    return <div className="reports-empty">No data available.</div>
  }

  const data = months.map((m) => ({
    month: m.month.slice(0, 7),
    Income: Number(m.income),
    Expenses: Number(m.expenses),
    Net: Number(m.net),
  }))

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
        <XAxis dataKey="month" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={(v: number) => formatMoney(v)} tick={{ fontSize: 11 }} width={80} />
        <Tooltip formatter={(v: unknown) => formatMoney(Number(v))} />
        <Legend />
        <Bar dataKey="Income" fill="#59a14f" />
        <Bar dataKey="Expenses" fill="#e15759" />
        <Bar dataKey="Net" fill="#4e79a7" />
      </BarChart>
    </ResponsiveContainer>
  )
}
