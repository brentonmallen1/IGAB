import { useRef, useState } from 'react'
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useSavingsRateReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_NEUTRAL, COLOR_POSITIVE } from './chartColors'
import { MetricCard } from '../MetricCard'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeButtons } from './rangeButtons'

interface Props {
  budgetId: string
}

const pct = (v: number | null) => (v === null ? '—' : `${(v * 100).toFixed(1)}%`)

export function SavingsRateReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney } = useFormatters()
  const [months, setMonths] = useState(12)
  const [withDebt, setWithDebt] = useState(true)
  const { data, isLoading, isError, error, refetch } = useSavingsRateReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const rows = data?.months ?? []
  const summary = data?.summary
  const rateKey = withDebt ? 'savings_rate_with_debt' : 'savings_rate'

  const chartData = rows.map((m) => ({
    date: m.month.slice(0, 7),
    Saved: Number(m.savings),
    'Debt Paid': Number(m.debt_principal),
    Spent: Number(m.spending),
    // null leaves a gap in the line rather than dropping it to zero, which
    // would read as "saved nothing" in a month with no income at all.
    'Savings Rate': m[rateKey] === null ? null : m[rateKey] * 100,
  }))

  const hasAnything = rows.some(
    (m) => Number(m.income) !== 0 || Number(m.savings) !== 0 || Number(m.debt_principal) !== 0
  )

  return (
    <div className="report-section surface">
      <div className="report-section__header">
        <h2 className="report-section__title">Savings Rate</h2>
        <ReportInfoButton title="Savings Rate">
          <p>How much of what came in you kept, month by month.</p>
          <p>
            <strong>Savings rate</strong> = money moved into savings ÷ income. With{' '}
            <em>“include debt payments”</em> on, money used to pay down a tracked debt counts too —
            both build what you own rather than consuming it.
          </p>
          <p>
            Growth <em>inside</em> a tracked account — dividends, market movement — is deliberately{' '}
            <strong>not</strong> counted. It changes your net worth, but you didn’t save it, and
            counting it would make this number climb in a good market while you did nothing.
          </p>
          <p>
            A month with no income shows a gap rather than 0%: having no income recorded isn’t the
            same as saving none of it.
          </p>
          <ReportScopeNote scope="on-budget" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Share of income kept</p>
        <div className="flex-row ms-auto">
          <ReportRangeButtons months={months} onChange={setMonths} />
          <button
            className={`report-btn ${withDebt ? 'report-btn--active' : ''}`}
            aria-pressed={withDebt}
            onClick={() => setWithDebt((v) => !v)}
            type="button"
            title="Count money used to pay down a tracked debt as saving"
          >
            Include debt payments
          </button>
          <ReportExportButton
            reportId="savings-rate"
            getRows={() =>
              rows.map((m) => ({
                month: m.month,
                income: Number(m.income),
                spending: Number(m.spending),
                savings: Number(m.savings),
                debt_principal: Number(m.debt_principal),
                savings_rate: m.savings_rate,
                savings_rate_with_debt: m.savings_rate_with_debt,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </div>

      <div ref={captureRef} className="report-capture">
        {summary && (
          <div className="report-metrics">
            <MetricCard
              label={withDebt ? 'Savings Rate (with debt)' : 'Savings Rate'}
              value={pct(withDebt ? summary.savings_rate_with_debt : summary.savings_rate)}
            />
            <MetricCard label="Income" value={formatMoney(Number(summary.income))} />
            <MetricCard label="Saved" value={formatMoney(Number(summary.savings))} />
            <MetricCard
              label="Debt Paid Down"
              value={formatMoney(Number(summary.debt_principal))}
            />
          </div>
        )}

        {!hasAnything ? (
          <div className="reports-empty">
            No income or savings recorded yet. Once money comes in and some of it moves to a savings
            or investment account, the rate appears here.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
              <YAxis
                yAxisId="money"
                tickFormatter={(v) => formatMoney(v)}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={90}
              />
              <YAxis
                yAxisId="rate"
                orientation="right"
                tickFormatter={(v) => `${v}%`}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={50}
              />
              <Tooltip
                content={<ChartTooltip showTotal={false} />}
                offset={16}
                isAnimationActive={false}
              />
              <Legend />
              <Bar yAxisId="money" dataKey="Saved" stackId="kept" fill={COLOR_POSITIVE} />
              <Bar yAxisId="money" dataKey="Debt Paid" stackId="kept" fill={COLOR_NEUTRAL} />
              <Bar yAxisId="money" dataKey="Spent" fill={COLOR_NEGATIVE} />
              <Line
                yAxisId="rate"
                type="monotone"
                dataKey="Savings Rate"
                stroke={COLOR_NET}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
