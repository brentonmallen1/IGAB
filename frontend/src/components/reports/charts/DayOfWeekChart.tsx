import {
  Bar, BarChart, CartesianGrid,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Cell,
} from 'recharts'
import { useReportStore } from '../../../stores/reportStore'
import { useDayPatternsReport } from '../../../api/reports'
import { formatMoney } from '../../../utils/money'
import { MetricCard } from '../MetricCard'
import { CHART_COLORS } from './chartColors'
import { ReportInfoButton } from '../ReportInfoButton'

interface Props { budgetId: string }

export function DayPatternsReport({ budgetId }: Props) {
  const { filters } = useReportStore()
  const catIds = filters.categoryIds.length > 0 ? filters.categoryIds : undefined
  const acctIds = filters.accountIds.length > 0 ? filters.accountIds : undefined
  const { data, isLoading } = useDayPatternsReport(budgetId, filters.startDate, filters.endDate, catIds, acctIds)

  if (isLoading) return <div className="report-loading">Loading…</div>

  const days = data?.days ?? []

  const maxDay = days.reduce((best, d) => (Number(d.total) > Number(best.total) ? d : best), days[0])
  const minDay = days.reduce((least, d) => (Number(d.total) < Number(least.total) ? d : least), days[0])

  const chartData = days.map((d) => ({
    name: d.day_name,
    Amount: Number(d.total),
    Transactions: d.count,
    avgPerTxn: d.count > 0 ? Number(d.total) / d.count : 0,
  }))

  return (
    <div className="report-section">
      <div className="report-section__controls">
        <h2 className="report-section__title">Day-of-Week Spending Patterns</h2>
        <ReportInfoButton title="Day-of-Week Patterns">
          <p>Total spending aggregated by day of week across all transactions in the selected period. The <strong>peak day is highlighted</strong> in a different color.</p>
          <p>High weekday spending often signals structured habits (groceries, work lunches). High weekend spending can indicate impulse or leisure spending. Use this to identify which days need more discipline.</p>
        </ReportInfoButton>
      </div>
      <p className="report-section__subtitle">
        When do you spend the most? Reveals impulse vs structured spending habits.
      </p>

      {days.length > 0 && maxDay && minDay && (
        <div className="report-metrics">
          <MetricCard label="Highest Spending Day" value={maxDay.day_name} sub={formatMoney(Number(maxDay.total))} />
          <MetricCard label="Lowest Spending Day" value={minDay.day_name} sub={formatMoney(Number(minDay.total))} />
        </div>
      )}

      {chartData.length === 0 ? (
        <div className="reports-empty">No spending data for this period.</div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => formatMoney(v)} tick={{ fontSize: 11 }} width={80} />
            <Tooltip
              formatter={(v: unknown, name: unknown) =>
                name === 'Amount' ? [formatMoney(Number(v)), name] : [Number(v), String(name)]
              }
              offset={16}
              isAnimationActive={false}
            />
            <Bar dataKey="Amount" radius={[3, 3, 0, 0]} barSize={44}>
              {chartData.map((entry, i) => {
                const isMax = maxDay && entry.name === maxDay.day_name
                return (
                  <Cell
                    key={i}
                    fill={isMax ? CHART_COLORS[1] : CHART_COLORS[0]}
                    fillOpacity={0.85}
                  />
                )
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
