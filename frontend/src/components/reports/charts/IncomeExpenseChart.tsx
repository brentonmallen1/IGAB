import { useRef } from 'react'
import {
  Bar,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  incomeDrill,
  spendingDrillClasses,
  useReportMonths,
  useReportStore,
} from '../../../stores/reportStore'
import { useIncomeExpenseReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { monthWindow } from '../../../utils/dateWindow'
import { DrillDownTable } from '../DrillDownTable'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_NEUTRAL, COLOR_POSITIVE } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import './IncomeExpenseChart.css'

interface Props {
  budgetId: string
}

export function IncomeExpenseReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const setDrillDown = useReportStore((s) => s.setDrillDown)
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useIncomeExpenseReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  function drillTo(month: string, direction: 'inflow' | 'outflow') {
    const ym = month.slice(0, 7)
    const window = monthWindow(ym)
    const range = { startDate: window.start, endDate: window.end }
    if (direction === 'inflow') {
      setDrillDown(incomeDrill(`Income · ${ym}`, range))
      return
    }
    setDrillDown({
      kind: 'month',
      label: `Expenses · ${ym}`,
      // Leaf + explicit classes: this bar means SPENDING (savings and debt
      // principal are separate series), so the panel must not list every
      // outflow. Classes live on leaves, not on a split parent, so the scope
      // has to match too.
      scope: 'leaf',
      direction,
      activityClasses: spendingDrillClasses(false),
      ...range,
    })
  }

  const monthBarClick = (direction: 'inflow' | 'outflow') => (data: unknown) => {
    const d = data as { month?: string; payload?: { month?: string } }
    const month = d.month ?? d.payload?.month
    if (month) drillTo(month, direction)
  }

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const chartData = (data?.months ?? []).map((m) => ({
    month: m.month.slice(0, 7),
    Income: m.income,
    Expenses: m.expenses,
    Saved: m.savings + m.debt_principal,
    Net: m.net,
  }))

  const tableRows = (data?.months ?? []).map((m) => ({
    id: m.month,
    name: m.month.slice(0, 7),
    // Positive is spending, under a column headed Expenses. A month whose
    // refunds exceeded its spending is negative and now READS negative: the
    // table used to abs() this, so "we got $40 back" drew as "we spent $40".
    amount: m.expenses,
    extra: `Net: ${formatMoney(m.net)}`,
  }))

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Income vs Expenses</h2>
        <ReportInfoButton title="Income vs Expenses">
          <p>
            Monthly <strong>income</strong> (green) vs <strong>expenses</strong> (red) as bars, with
            the <strong>net cash flow</strong> (blue line) overlaid.
          </p>
          <p>
            <strong>Saved</strong> is money that left the budget but stayed yours — moved into
            savings or investments, or used to pay down a tracked debt. It sits beside expenses
            rather than inside them, because it isn't money spent.
          </p>
          <p>
            Months where the blue line is above zero mean you spent less than you earned — a
            positive sign. Dipping below zero means you ran a deficit that month.
          </p>
          <ReportScopeNote report="income-expense" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
          <ReportExportButton
            reportId="income-expense"
            getRows={() =>
              (data?.months ?? []).map((m) => ({
                month: m.month.slice(0, 7),
                income: m.income,
                expenses: m.expenses,
                savings: m.savings,
                debt_principal: m.debt_principal,
                net: m.net,
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
              <YAxis
                tickFormatter={moneyAxis.tickFormatter}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={moneyAxis.width}
              />
              <Tooltip
                content={<ChartTooltip showTotal={false} formatter={formatMoney} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <Bar
                dataKey="Income"
                fill={COLOR_POSITIVE}
                radius={[2, 2, 0, 0]}
                cursor="pointer"
                onClick={monthBarClick('inflow')}
              />
              <Bar
                dataKey="Expenses"
                fill={COLOR_NEGATIVE}
                radius={[2, 2, 0, 0]}
                cursor="pointer"
                onClick={monthBarClick('outflow')}
              />
              <Bar dataKey="Saved" fill={COLOR_NEUTRAL} radius={[2, 2, 0, 0]} />
              <Line
                dataKey="Net"
                stroke={COLOR_NET}
                strokeWidth={2}
                dot={{ r: 3 }}
                type="monotone"
              />
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
