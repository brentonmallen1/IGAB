import { useRef, useState } from 'react'
import {
  Bar,
  CartesianGrid,
  Cell,
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
import { MIXED_SIGN_STACK } from './mixedSignStack'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { SavingsRateDialog } from '../SavingsRateDialog'
import { SAVED_DEFINITION } from '../savingsRateBreakdown'
import { pct, RATE_SERIES, ratePercent, savingsRateTooltipWith } from './savingsRateView'
import { useReportMonths } from '../../../stores/reportStore'
import {
  completeMonthRows,
  monthRange,
  reportMonthLabel,
  RUNNING_MONTH_OPACITY,
} from '../../../utils/reportMonths'
import { GuideTabLink } from '../../guide/GuideTabLink'

interface Props {
  budgetId: string
}

export function SavingsRateReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(320)
  const { formatMoney, formatMonthShort } = useFormatters()
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
    iso: m.month,
    date: reportMonthLabel(m.month, m.partial_month, formatMonthShort),
    partial: m.partial_month,
    Saved: Number(m.savings),
    'Debt Paid': Number(m.debt_principal),
    Spent: Number(m.spending),
    // null leaves a gap in the line rather than dropping it to zero, which
    // would read as "saved nothing" in a month with no income at all. The
    // running month has no rate either: its bills are in and its pay may not
    // be, so a mid-month rate is the calendar talking — its bars say so far.
    [RATE_SERIES]: m[rateKey] === null || m.partial_month ? null : ratePercent(m[rateKey]),
  }))
  // The summary is the complete months alone, served; the card says which.
  const complete = completeMonthRows(rows)
  const covered = monthRange(complete[0]?.month, complete.at(-1)?.month, formatMonthShort)

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
            <strong>Savings rate</strong> = saved ÷ income. {SAVED_DEFINITION} Assigning to an
            envelope that counts while it’s in the budget counts as saved, spending from it lowers
            saved, and moving its money on to a savings account nets to zero. With{' '}
            <em>“include debt payments”</em> on, money used to pay down a tracked debt counts too —
            both build what you own rather than consuming it.
          </p>
          <p>
            Growth <em>inside</em> a tracked account — dividends, market movement — is deliberately{' '}
            <strong>not</strong> counted. It changes your net worth, but you didn’t save it, and
            counting it would make this number climb in a good market while you did nothing.
          </p>
          <p>
            Of your tracked accounts, only one that <strong>counts as savings</strong> is saving.
            Selling a car or a house tracked as an asset counts as income, and buying one as
            spending — turn the setting off on the account for things like that.
          </p>
          <p>
            A month with no income shows a gap rather than 0%: having no income recorded isn’t the
            same as saving none of it.
          </p>
          <p>
            The headline covers the picker&apos;s complete months. The month in progress is drawn
            after them, lighter and marked <em>so far</em>, with no rate: until its pay has landed a
            partial month&apos;s rate says more about the calendar than about saving.
          </p>
          <p>
            Open the rate to see where the savings went, what paid down debt and where the income
            came from.
          </p>
          <p>
            <GuideTabLink tab="aside" anchor="savings-modes">
              How Savings envelopes count
            </GuideTabLink>
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
                partial_month: m.partial_month,
                income: Number(m.income),
                spending: Number(m.spending),
                savings: Number(m.savings),
                savings_moved: Number(m.savings_moved),
                savings_held: Number(m.savings_held),
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
              sub={covered ?? undefined}
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
            No income or savings recorded yet. Once money comes in and some of it is saved — moved
            to a savings or investment account, or held in a Savings envelope — the rate appears
            here.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            {/* Saved goes negative in a month that drew money back out of
                savings, and Debt Paid stacks on it. */}
            <ComposedChart
              data={chartData}
              {...MIXED_SIGN_STACK}
              margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
            >
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
              {(
                [
                  ['Saved', COLOR_POSITIVE, 'kept'],
                  ['Debt Paid', COLOR_NEUTRAL, 'kept'],
                  ['Spent', COLOR_NEGATIVE, undefined],
                ] as const
              ).map(([key, fill, stackId]) => (
                <Bar key={key} yAxisId="money" dataKey={key} stackId={stackId} fill={fill}>
                  {chartData.map((d) => (
                    <Cell key={d.iso} fillOpacity={d.partial ? RUNNING_MONTH_OPACITY : 1} />
                  ))}
                </Bar>
              ))}
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
