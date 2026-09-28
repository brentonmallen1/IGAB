import { useRef } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useNetWorthReport } from '../../../api/reports'
import { useChartHeight } from '../../../hooks/useChartHeight'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { ReportErrorState } from '../ReportErrorState'
import { ChartTooltip } from './ChartTooltip'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { COLOR_NEGATIVE, COLOR_NET, COLOR_POSITIVE } from './chartColors'
import { ReportInfoButton, ReportScopeNote } from '../ReportInfoButton'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ReportRangeSelect } from './rangeSelect'
import { useReportMonths } from '../../../stores/reportStore'
import { arrivalMarks, likeForLikeLine } from '../../../utils/trackingStart'
import { arrivalLines } from './arrivalLines'
import { TrackingStartNote } from './TrackingStartNote'
import { staleNote, statedNote } from './netWorthView'
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

export function NetWorthReport({ budgetId }: Props) {
  const chartHeight = useChartHeight(340)
  const { formatMoney, formatMonthShort, formatDate } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useNetWorthReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />

  const points = data?.points ?? []
  const latest = points[points.length - 1]
  const marks = arrivalMarks(points, formatMoney)
  const change = data
    ? likeForLikeLine(data.like_for_like_change, data.entered_total, data.change, formatMoney)
    : null
  const assetsNote = data
    ? statedNote(data.stated_values, 'stated_asset', formatMoney, formatDate)
    : null
  const debtsNote = data
    ? statedNote(data.stated_values, 'manual_debt', formatMoney, formatDate)
    : null
  const stale = data ? staleNote(data.stale_balances, data.stale_after_days, formatDate) : null

  const chartData = points.map((p) => ({
    date: formatMonthShort(p.date),
    Assets: p.total_assets,
    Liabilities: p.total_liabilities,
    'Net Worth': p.net_worth,
  }))

  return (
    <div className="report-section surface">
      <ReportHeader>
        <h2 className="report-section__title">Net Worth Over Time</h2>
        <ReportInfoButton title="Net Worth Over Time">
          <p>
            <strong>Net worth</strong> = assets minus liabilities. <strong>Assets</strong> are what
            every account holds — on-budget and tracking alike — plus the stated value of things
            with no account behind them, like a home. <strong>Liabilities</strong> are what cards
            and loans owe, plus debts you track by hand; both are subtracted.
          </p>
          <p>
            Each point is the balance at the end of its month; the last is today. The three lines
            are drawn over each other from zero, not stacked, and straight between points — a
            balance is known at each point, not in between.
          </p>
          <p>
            <strong>Started tracking</strong>: a numbered line marks a month something began being
            counted — an account linked with the balance it already had (its Starting Balance, and
            any history from before its budget start), or a home or a debt given its first value.
            That is the register filling in, not money you made or lost, so{' '}
            <strong>Change, like-for-like</strong> leaves it out: the change over the range less
            everything that began being counted after its first month.
          </p>
          <p>
            A stated value counts from the date it was entered, and a balance that has not moved in{' '}
            {data?.stale_after_days ?? 60} days is listed under the chart — flat there means nothing
            updated it.
          </p>
          <ReportScopeNote report="net-worth" />
        </ReportInfoButton>
        <div className="flex-row ms-auto">
          <ReportRangeSelect />
          <ReportExportButton
            reportId="net-worth"
            getRows={() =>
              points.map((p) => ({
                date: p.date,
                assets: p.total_assets,
                liabilities: p.total_liabilities,
                net_worth: p.net_worth,
                started_tracking: p.entered,
              }))
            }
            captureRef={captureRef}
          />
        </div>
      </ReportHeader>

      <div ref={captureRef} className="report-capture">
        {latest && (
          <MetricRow>
            <MetricCard label="Current Net Worth" value={formatMoney(latest.net_worth)} />
            {change && (
              <MetricCard label="Change, like-for-like" value={change.value} sub={change.sub} />
            )}
            <MetricCard label="Total Assets" value={formatMoney(latest.total_assets)} />
            <MetricCard label="Total Liabilities" value={formatMoney(latest.total_liabilities)} />
          </MetricRow>
        )}
        {debtsNote && <p className="report-section__subtitle">{debtsNote}</p>}
        {assetsNote && <p className="report-section__subtitle">{assetsNote}</p>}

        {chartData.length === 0 ? (
          <div className="reports-empty">No account data available.</div>
        ) : (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <AreaChart data={chartData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="nw-assets" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLOR_POSITIVE} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={COLOR_POSITIVE} stopOpacity={0.05} />
                </linearGradient>
                <linearGradient id="nw-net" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLOR_NET} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={COLOR_NET} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
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
              {arrivalLines(marks, (i) => chartData[i].date)}
              <Area
                type="linear"
                dataKey="Assets"
                stroke={COLOR_POSITIVE}
                fill="url(#nw-assets)"
                strokeWidth={2}
              />
              <Area
                type="linear"
                dataKey="Liabilities"
                stroke={COLOR_NEGATIVE}
                fill="none"
                strokeWidth={2}
                strokeDasharray="5 3"
              />
              <Area
                type="linear"
                dataKey="Net Worth"
                stroke={COLOR_NET}
                fill="url(#nw-net)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
        <TrackingStartNote
          marks={marks}
          formatMoney={formatMoney}
          formatMonthShort={formatMonthShort}
        />
        {stale && (
          <p className="report-note" role="note">
            {stale}
          </p>
        )}
      </div>
    </div>
  )
}
