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
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_NEUTRAL, COLOR_POSITIVE } from './chartColors'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { SavingsRateDialog } from '../SavingsRateDialog'
import { pct, RATE_SERIES, ratePercent, savingsRateTooltipWith } from './savingsRateView'
import { useReportMonths } from '../../../stores/reportStore'

interface Props {
  budgetId: string
}

export function SavingsRateReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const savingsRateTooltip = savingsRateTooltipWith(formatMoney)
  const months = useReportMonths()
  const [withDebt, setWithDebt] = useState(true)
  const [contributorsOpen, setContributorsOpen] = useState(false)
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
    [RATE_SERIES]: m[rateKey] === null ? null : ratePercent(m[rateKey]),
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
          <p>
            Open the rate to see where the savings went, what paid down debt and where the income
            came from.
          </p>
          <ReportScopeNote report="savings-rate" />
        </ReportInfoButton>
        <p className="report-section__subtitle">Share of income kept</p>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
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
          <MetricRow>
            <MetricCard
              label={withDebt ? 'Savings Rate (with debt)' : 'Savings Rate'}
              value={pct(summary[rateKey])}
              details={{
                label: `Savings rate ${pct(summary[rateKey])}. Show what contributed`,
                onOpen: () => setContributorsOpen(true),
              }}
            />
            <MetricCard label="Income" value={formatMoney(Number(summary.income))} />
            <MetricCard label="Saved" value={formatMoney(Number(summary.savings))} />
            <MetricCard
              label="Debt Paid Down"
              value={formatMoney(Number(summary.debt_principal))}
            />
          </MetricRow>
        )}
        {data && contributorsOpen && (
          // The window the summary covers, as served — so the dialog's totals
          // are this card's, not a range rebuilt from `months`.
          <SavingsRateDialog
            budgetId={budgetId}
            startDate={data.start_date}
            endDate={data.end_date}
            rate={data.summary[rateKey]}
            withDebt={withDebt}
            onClose={() => setContributorsOpen(false)}
          />
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
                tickFormatter={moneyAxis.tickFormatter}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={moneyAxis.width}
              />
              <YAxis
                yAxisId="rate"
                orientation="right"
                tickFormatter={(v) => `${v}%`}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                width={50}
              />
              <Tooltip
                content={<ChartTooltip showTotal={false} formatter={savingsRateTooltip} />}
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
                dataKey={RATE_SERIES}
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
