import { useState } from 'react'
import {
  Bar, ComposedChart, CartesianGrid, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { useIncomeExpenseReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { DrillDownTable } from '../DrillDownTable'
import { ChartTooltip } from './ChartTooltip'
import { buildExportUrl } from '../../../api/reports'
import { ReportInfoButton } from '../ReportInfoButton'
import './IncomeExpenseChart.css'

interface Props { budgetId: string }

export function IncomeExpenseReport({ budgetId }: Props) {
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useIncomeExpenseReport(budgetId, months)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const chartData = (data?.months ?? []).map((m) => ({
    month: m.month.slice(0, 7),
    Income: Number(m.income),
    Expenses: Number(m.expenses),
    Net: Number(m.net),
  }))

  const tableRows = (data?.months ?? []).map((m) => ({
    id: m.month,
    name: m.month.slice(0, 7),
    amount: -Number(m.expenses),
    extra: `Net: ${formatMoney(Number(m.net))}`,
  }))

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Income vs Expenses</h2>
        <ReportInfoButton title="Income vs Expenses">
          <p>Monthly <strong>income</strong> (green) vs <strong>expenses</strong> (red) as bars, with the <strong>net cash flow</strong> (blue line) overlaid.</p>
          <p>Months where the blue line is above zero mean you spent less than you earned — a positive sign. Dipping below zero means you ran a deficit that month.</p>
        </ReportInfoButton>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          {([3, 6, 12, 24] as const).map((m) => (
            <button
              key={m}
              className={`report-btn ${months === m ? 'report-btn--active' : ''}`}
              onClick={() => setMonths(m)}
              type="button"
            >
              {m}mo
            </button>
          ))}
          <a className="report-btn" href={buildExportUrl(budgetId, 'csv')} download>Export CSV</a>
        </div>
      </div>
      {chartData.length === 0 ? (
        <div className="reports-empty">No data for this period.</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={90} />
              <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
              <Legend />
              <Bar dataKey="Income" fill="#59a14f" radius={[2, 2, 0, 0]} />
              <Bar dataKey="Expenses" fill="#e15759" radius={[2, 2, 0, 0]} />
              <Line dataKey="Net" stroke="#4e79a7" strokeWidth={2} dot={{ r: 3 }} type="monotone" />
            </ComposedChart>
          </ResponsiveContainer>
          <DrillDownTable rows={tableRows} amountLabel="Expenses" />
        </>
      )}
    </div>
  )
}
