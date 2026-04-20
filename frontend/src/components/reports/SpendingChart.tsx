import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { formatMoney } from '../../utils/money'
import type { SpendingCategory } from '../../types'

const COLORS = [
  '#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
  '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac',
]

interface Props {
  categories: SpendingCategory[]
  total: number
}

export function SpendingChart({ categories, total }: Props) {
  if (categories.length === 0) {
    return <div className="reports-empty">No spending data for this period.</div>
  }

  const data = categories.map((c) => ({ name: c.name, value: Number(c.total) }))

  return (
    <div className="spending-chart">
      <div className="spending-chart__total">
        Total spending: <strong>{formatMoney(total)}</strong>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            outerRadius={110}
            dataKey="value"
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(1)}%`}
            labelLine={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v: number) => formatMoney(v)} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
      <table className="spending-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Group</th>
            <th className="num">Amount</th>
            <th className="num">%</th>
          </tr>
        </thead>
        <tbody>
          {categories.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td className="muted">{c.group_name}</td>
              <td className="num">{formatMoney(Number(c.total))}</td>
              <td className="num">{c.pct.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
