import { useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useEmergencyCoverageReport } from '../../../api/reports'
import { useFormatters } from '../../../hooks/useFormatters'
import { MetricCard } from '../MetricCard'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { COLOR_NET, COLOR_POSITIVE, COLOR_NEUTRAL } from './chartColors'
import { carriedFlatFrom, coverageTrend, monthsToTarget, standing } from './coverageView'
import { useReportMonths } from '../../../stores/reportStore'
import { useMoneyAxis } from './useMoneyAxis'
import './EmergencyCoverageReport.css'

interface Props {
  budgetId: string
}

/**
 * Whether the emergency fund covers a lean month, and for how long.
 *
 * The Essentials report answers what a lean month costs and carries today's
 * runway as one card's subtitle. This is the other question — *am I covered,
 * and is that getting better* — which is a stock measured against a flow, and
 * neither half belongs on a chart of monthly spending. Putting a fund balance
 * beside spending bars invites reading them as comparable when they are not.
 *
 * Every figure here is served (`services/emergency_coverage.py`), including
 * the headline coverage, which is the Essentials report's own `runway_months`
 * quoted rather than recomputed: two pages that each divide the same pair of
 * numbers are two pages that can disagree.
 */
/** The first chart's Y axis is months of runway, not money.
 *
 * The shared tooltip's old default rendered 3.4 months as "$3.40".
 */
function monthsCovered(value: number): string {
  return `${value.toFixed(1)} months`
}

/** The same axis's ticks: a bare count, labelled "months" beside it. */
function monthsTick(value: number): string {
  return String(value)
}

export function EmergencyCoverageReport({ budgetId }: Props) {
  const { formatMoney, formatMonth } = useFormatters()
  // The second chart plots money. Its axis printed raw numbers — no currency
  // and no privacy mask — beside a tooltip and cards that both read $••••.
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useEmergencyCoverageReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return <div className="reports-empty">No data available.</div>

  const [low, high] = data.target_range
  const where = standing(data.coverage_months, data.target_range)
  const trend = coverageTrend(data.series)
  const toTarget = monthsToTarget(data.series)
  const chart = data.series.map((p) => ({
    month: p.month.slice(0, 7),
    Covered: p.coverage_months,
    Fund: p.fund_balance,
    [`${low}-month target`]: p.target_low,
    [`${high}-month target`]: p.target_high,
  }))
  const carriedFrom = carriedFlatFrom(data.series)

  return (
    <div className="coverage-report">
      <div className="coverage-report__section surface">
        <div className="report-section__header">
          <h2 className="report-section__title">Emergency Fund</h2>
          <ReportInfoButton title="Emergency Fund">
            <p>
              How many months of <strong>essential</strong> spending your emergency fund would
              cover. Coverage is the fund divided by a trailing three-month average of essentials —
              the same 90-day window the Guide’s target uses, so this page and the roadmap cannot
              tell different stories about the same household.
            </p>
            <p>
              The target moves. {low} months of essentials is not a fixed sum: as spending grows the
              target grows with it, and a fund standing still can lose coverage without losing a
              cent. That is why the second chart draws the band per month rather than as one line.
            </p>
            <p>
              The roadmap suggests {low}–{high} months once expensive debt is gone.
            </p>
          </ReportInfoButton>
          <div className="flex-row ms-auto">
            <ReportRangeSelect />
            <ReportExportButton
              reportId="emergency-fund"
              getRows={() =>
                data.series.map((p) => ({
                  month: p.month,
                  fund_balance: p.fund_balance,
                  essentials: p.essentials,
                  coverage_months: p.coverage_months,
                  target_low: p.target_low,
                }))
              }
              captureRef={captureRef}
            />
          </div>
        </div>

        {!data.tagged ? (
          <div className="coverage-report__empty">
            <p>
              Nothing is tagged <strong>Essential</strong> yet, so there is no lean month to measure
              a fund against. Tag a category in its inspector on the Budget page and this report
              fills in — the <Link to="/reports?tab=essentials">Essentials report</Link> explains
              what to tag.
            </p>
          </div>
        ) : data.fund_balance === null ? (
          <div className="coverage-report__empty">
            <p>
              No emergency fund found yet. IGAB looks for a savings-tagged envelope whose name
              mentions an emergency, then savings accounts — deliberately narrow, because telling
              someone they are covered when they are not is the worse mistake.
            </p>
            <p>
              Point the <Link to="/guide">Guide</Link> at whatever you actually keep set aside —
              including money at another bank — and every figure here fills in.
            </p>
          </div>
        ) : (
          <div ref={captureRef}>
            <MetricRow>
              <MetricCard
                label="Covered"
                value={data.coverage_months === null ? '—' : `${data.coverage_months} months`}
                sub={
                  trend
                    ? `${trend.delta >= 0 ? '+' : ''}${trend.delta} months over ${trend.months} months`
                    : undefined
                }
                accent={where === 'within' || where === 'above'}
                warning={where === 'below'}
              />
              <MetricCard
                label="Fund"
                value={formatMoney(data.fund_balance)}
                sub={data.fund_source ?? undefined}
              />
              <MetricCard
                label={`${low}-month target`}
                value={formatMoney(data.target_low)}
                sub={
                  data.fund_balance >= data.target_low
                    ? 'Reached'
                    : `${formatMoney(data.target_low - data.fund_balance)} to go`
                }
                accent={data.fund_balance >= data.target_low}
              />
              <MetricCard
                label={`${high}-month target`}
                value={formatMoney(data.target_high)}
                sub={
                  data.fund_balance >= data.target_high
                    ? 'Reached'
                    : `${formatMoney(data.target_high - data.fund_balance)} to go`
                }
                accent={data.fund_balance >= data.target_high}
              />
              {toTarget !== null && (
                <MetricCard
                  label={`At this pace`}
                  value={`${toTarget} month${toTarget === 1 ? '' : 's'}`}
                  sub={`to ${low} months covered`}
                />
              )}
            </MetricRow>

            <p className="coverage-report__note">
              Coverage is the fund divided by a trailing three-month average of essential spending —{' '}
              {formatMoney(data.essentials_monthly)}/month over the Guide’s 90-day window. The{' '}
              <Link to="/reports?tab=essentials">Essentials report</Link> breaks that figure down by
              category.
              {carriedFrom !== null && (
                <>
                  {' '}
                  The self-reported part of your fund ({formatMoney(data.external_amount ?? 0)}) is
                  carried flat from {formatMonth(carriedFrom)}: IGAB cannot know what another bank
                  held before then.
                </>
              )}
            </p>

            <h3 className="coverage-report__chart-title">Months covered</h3>
            <div className="coverage-report__chart">
              <ResponsiveContainer width="100%" height={240}>
                <ComposedChart data={chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <YAxis
                    tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                    tickFormatter={monthsTick}
                    label={{
                      value: 'months',
                      angle: -90,
                      position: 'insideLeft',
                      fontSize: 11,
                      fill: 'var(--text-muted)',
                    }}
                  />
                  {/* The band, not two lines: the roadmap suggests a range,
                      and drawing it as a range is what stops 3 reading as a
                      pass mark and 6 as a failure to hit it. */}
                  <ReferenceArea
                    y1={low}
                    y2={high}
                    fill={COLOR_POSITIVE}
                    fillOpacity={0.1}
                    stroke="none"
                  />
                  <Tooltip content={<ChartTooltip formatter={monthsCovered} />} />
                  <Line
                    type="monotone"
                    dataKey="Covered"
                    stroke={COLOR_NET}
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <h3 className="coverage-report__chart-title">Fund against a moving target</h3>
            <div className="coverage-report__chart">
              <ResponsiveContainer width="100%" height={240}>
                <ComposedChart data={chart}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <YAxis {...moneyAxis} tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                  <Tooltip content={<ChartTooltip formatter={formatMoney} />} />
                  <Area
                    type="monotone"
                    dataKey="Fund"
                    stroke={COLOR_NET}
                    fill={COLOR_NET}
                    fillOpacity={0.15}
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey={`${low}-month target`}
                    stroke={COLOR_POSITIVE}
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey={`${high}-month target`}
                    stroke={COLOR_NEUTRAL}
                    strokeWidth={1.5}
                    strokeDasharray="4 3"
                    dot={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <table className="coverage-report__table">
              <caption className="sr-only">
                Emergency fund coverage by month. The accessible view of both charts above.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Fund</th>
                  <th scope="col">Essentials / mo</th>
                  <th scope="col">Covered</th>
                  <th scope="col">{low}-month target</th>
                </tr>
              </thead>
              <tbody>
                {data.series.map((p) => (
                  <tr key={p.month}>
                    <th scope="row">{formatMonth(p.month)}</th>
                    <td>{formatMoney(p.fund_balance)}</td>
                    <td>{formatMoney(p.essentials)}</td>
                    <td>{p.coverage_months === null ? '—' : `${p.coverage_months}`}</td>
                    <td>{formatMoney(p.target_low)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
