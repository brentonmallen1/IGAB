import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Cell,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { usePayeeAnalysisReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { DrillDownTable } from '../DrillDownTable'
import { MetricCard } from '../MetricCard'
import { CHART_COLORS, chartColor } from './chartColors'
import { ReportInfoButton } from '../ReportInfoButton'

interface Props { budgetId: string }

export function PayeeReport({ budgetId }: Props) {
  const { filters } = useReportStore()
  const payeeIds = filters.payeeIds.length > 0 ? filters.payeeIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading } = usePayeeAnalysisReport(budgetId, filters.startDate, filters.endDate, 25, payeeIds, acctIds)
  const [view, setView] = useState<'top' | 'recurring'>('top')

  if (isLoading) return <div className="report-loading">Loading…</div>

  const payees = data?.payees ?? []
  const recurring = payees.filter((p) => p.is_recurring)
  const displayed = view === 'recurring' ? recurring : payees.slice(0, 20)

  const chartData = displayed.map((p) => ({
    name: p.payee_name.length > 18 ? p.payee_name.slice(0, 16) + '…' : p.payee_name,
    Amount: Number(p.total),
    Visits: p.transaction_count,
    isRecurring: p.is_recurring,
  }))

  const tableRows = displayed.map((p) => ({
    id: p.payee_id,
    name: p.payee_name,
    subName: p.is_recurring ? 'Recurring' : `${p.transaction_count} transactions`,
    amount: -Number(p.total),
    pct: Number(p.pct),
  }))

  const grandTotal = payees.reduce((s, p) => s + Number(p.total), 0)

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Payee Analysis</h2>
        <ReportInfoButton title="Payee Analysis">
          <p>Ranks your top payees by total spending in the selected period. <strong>Highlighted bars</strong> indicate recurring payees (appeared in 3+ different months).</p>
          <p>Use <em>Recurring</em> mode to focus only on fixed or habitual expenses — subscriptions, utilities, regular vendors. These are the easiest targets for cutting predictable spending.</p>
        </ReportInfoButton>
        <p className="report-section__subtitle" style={{ margin: 0 }}>
          Top payees by spending. Recurring = appeared in 3+ months.
        </p>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button
            className={`report-btn ${view === 'top' ? 'report-btn--active' : ''}`}
            onClick={() => setView('top')}
            type="button"
          >
            Top 20
          </button>
          <button
            className={`report-btn ${view === 'recurring' ? 'report-btn--active' : ''}`}
            onClick={() => setView('recurring')}
            type="button"
          >
            Recurring ({recurring.length})
          </button>
        </div>
      </div>

      {payees.length > 0 && (
        <div className="report-metrics">
          <MetricCard label="Total Payees" value={String(payees.length)} />
          <MetricCard label="Recurring Payees" value={String(recurring.length)} />
          <MetricCard label="Total Spent" value={formatMoney(grandTotal)} />
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No spending data for this period.</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 34)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 80, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={140} />
              <Tooltip
                formatter={(v: number, name: string) =>
                  name === 'Amount' ? [formatMoney(v), name] : [v, name]
                }
                offset={16}
                isAnimationActive={false}
              />
              <Bar dataKey="Amount" barSize={14} radius={[0, 2, 2, 0]}>
                {chartData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.isRecurring ? CHART_COLORS[2] : chartColor(i)}
                    fillOpacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <DrillDownTable rows={tableRows} total={grandTotal} />
        </>
      )}
    </div>
  )
}
