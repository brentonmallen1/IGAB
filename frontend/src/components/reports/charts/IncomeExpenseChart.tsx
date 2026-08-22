import { useRef, useState } from 'react'
import {
  Bar, ComposedChart, CartesianGrid, Legend, Line,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { useIncomeExpenseReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { monthWindow } from '../../../utils/dateWindow'
import { DrillDownTable } from '../DrillDownTable'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_NEUTRAL, COLOR_POSITIVE } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import './IncomeExpenseChart.css'

interface Props { budgetId: string }

export function IncomeExpenseReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const [months, setMonths] = useState(12)
  const { data, isLoading, isError, refetch } = useIncomeExpenseReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  function drillTo(month: string, direction: 'inflow' | 'outflow') {
    const ym = month.slice(0, 7)
    const window = monthWindow(ym)
    setDrillDown({
      kind: 'month',
      label: `${direction === 'inflow' ? 'Income' : 'Expenses'} · ${ym}`,
      scope: 'parent', direction,
      startDate: window.start, endDate: window.end,
    })
  }

  const monthBarClick = (direction: 'inflow' | 'outflow') => (data: unknown) => {
    const d = data as { month?: string; payload?: { month?: string } }
    const month = d.month ?? d.payload?.month
    if (month) drillTo(month, direction)
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState onRetry={() => refetch()} />

  const chartData = (data?.months ?? []).map((m) => ({
    month: m.month.slice(0, 7),
    Income: Number(m.income),
    Expenses: Number(m.expenses),
    Saved: Number(m.savings) + Number(m.debt_principal),
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
      <div className="report-section__header">
        <h2 className="report-section__title">Income vs Expenses</h2>
        <ReportInfoButton title="Income vs Expenses">
          <p>Monthly <strong>income</strong> (green) vs <strong>expenses</strong> (red) as bars, with the <strong>net cash flow</strong> (blue line) overlaid.</p>
          <p><strong>Saved</strong> is money that left the budget but stayed yours — moved into savings or investments, or used to pay down a tracked debt. It sits beside expenses rather than inside them, because it isn't money spent.</p>
          <p>Months where the blue line is above zero mean you spent less than you earned — a positive sign. Dipping below zero means you ran a deficit that month.</p>
          <ReportScopeNote scope="on-budget" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
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
          <ReportExportButton
            reportId="income-expense"
            getRows={() =>
              (data?.months ?? []).map((m) => ({
                month: m.month.slice(0, 7),
                income: Number(m.income),
                expenses: Number(m.expenses),
                savings: Number(m.savings),
                debt_principal: Number(m.debt_principal),
                net: Number(m.net),
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>
      {chartData.length === 0 ? (
        <div className="reports-empty">No data for this period.</div>
      ) : (
        <div ref={captureRef} className="report-capture">
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={90} />
              <Tooltip content={<ChartTooltip showTotal={false} />} offset={16} isAnimationActive={false} />
              <Legend />
              <Bar dataKey="Income" fill={COLOR_POSITIVE} radius={[2, 2, 0, 0]} cursor="pointer" onClick={monthBarClick('inflow')} />
              <Bar dataKey="Expenses" fill={COLOR_NEGATIVE} radius={[2, 2, 0, 0]} cursor="pointer" onClick={monthBarClick('outflow')} />
              <Bar dataKey="Saved" fill={COLOR_NEUTRAL} radius={[2, 2, 0, 0]} />
              <Line dataKey="Net" stroke={COLOR_NET} strokeWidth={2} dot={{ r: 3 }} type="monotone" />
            </ComposedChart>
          </ResponsiveContainer>
          <DrillDownTable
            rows={tableRows}
            amountLabel="Expenses"
            onRowClick={(row) => drillTo(row.id, 'outflow')}
          />
        </div>
      )}
    </div>
  )
}
