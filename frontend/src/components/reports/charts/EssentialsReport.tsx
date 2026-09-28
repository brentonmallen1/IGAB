import { useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useEssentialsReport } from '../../../api/reports'
import { EmergencyFundCounting } from '../../emergencyFund/EmergencyFundCounting'
import { otherFigureNote, spreadsBills } from '../../../utils/essentialsFigures'
import { SpreadSinkingFundsToggle } from '../../common/SpreadSinkingFundsToggle/SpreadSinkingFundsToggle'
import { useFormatters } from '../../../hooks/useFormatters'
import { useMoneyAxis } from '../../../hooks/useMoneyAxis'
import { MetricCard } from '../MetricCard'
import { ReportNotes } from '../ReportNotes'
import { MetricRow } from '../MetricRow'
import { ReportInfoButton } from '../ReportInfoButton'
import { ReportErrorState } from '../ReportErrorState'
import { ReportRangeSelect } from './rangeSelect'
import { ReportExportButton } from '../ReportExportButton/ReportExportButton'
import { ChartTooltip } from './ChartTooltip'
import { CHART_COLORS, COLOR_NET } from './chartColors'
import { columnTotal, shareOfLeanMonth, worstMonth, worstOverHeadline } from './essentialsView'
import { monthRange } from '../../../utils/reportMonths'
import { fundCoverLine } from '../../../utils/runway'
import { completeMonths } from './averagedOver'
import { GuideTabLink } from '../../guide/GuideTabLink'
import './EssentialsReport.css'
import { useReportMonths } from '../../../stores/reportStore'
import { ReportHeader } from '../ReportHeader'

interface Props {
  budgetId: string
}

/**
 * What a lean month costs, from what the household tagged Essential — and
 * what a reserve of one, three, six or twelve months of it would be.
 *
 * One figure, three readers: the headline here is the Guide's
 * essential-expenses signal (the last three complete months, with Long-term
 * expense bills spread over twelve months when the budget's setting is on —
 * the number its emergency-fund target is built from) and the Overview card's. Both figures
 * are served; the one the setting does not pick is shown beside it. The table
 * averages complete months instead, so a partial current month cannot drag
 * every category down. Nothing self-reported from the Guide appears here.
 */
export function EssentialsReport({ budgetId }: Props) {
  const { formatMoney, formatMoneyOrDash, formatMonthShort } = useFormatters()
  const moneyAxis = useMoneyAxis()
  const months = useReportMonths()
  const { data, isLoading, isError, error, refetch } = useEssentialsReport(budgetId, months)
  const captureRef = useRef<HTMLDivElement>(null)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return <div className="reports-empty">No data available.</div>

  const [rangeLow, rangeHigh] = data.roadmap_range
  // The months the table divided by — the setting, or fewer on a budget
  // younger than it. Quoting the setting said "the last 12" over three.
  const averaged = data.months_averaged
  const averagedMonths = completeMonths(averaged)
  const headline = data.essentials.monthly
  const other = otherFigureNote(data.essentials, formatMoney)
  const worst = worstMonth(data.monthly_series)
  const spreading = spreadsBills(data.essentials, data.long_term_essentials)
  const worstOver = worst ? worstOverHeadline(worst.total, headline) : null
  // The months the headline averages, named wherever it is quoted.
  const headlineMonths =
    monthRange(data.essentials.window_start, data.essentials.window_end, formatMonthShort) ??
    'the last 3 complete months'
  const monthData = data.monthly_series.map((m) => ({
    month: formatMonthShort(m.month),
    Spent: m.total,
  }))

  return (
    <div className="essentials-report">
      <div className="essentials-report__section surface">
        <ReportHeader>
          <h2 className="report-section__title">Essentials</h2>
          <ReportInfoButton title="Essentials">
            <p>
              Spending in categories tagged <strong>Essential</strong> — the things you could not
              cut in an emergency. The narrower of the two necessity tiers: the Cost of Living
              report adds what is committed but sheddable, and shows the difference. The headline is
              the last three complete months averaged — the same figure the Guide’s emergency-fund
              target uses — so a monthly bill is in it three times whatever the day; the table
              averages the last {averagedMonths}.
            </p>
            <p>
              With <strong>Spread yearly bills over 12 months</strong> on, bills in categories
              tagged Long-term expense count as a twelfth of the last twelve complete months’ a
              month instead of when they were paid, so an annual premium does not inflate one
              quarter and vanish from the next. Both figures are shown; the chart and the table stay
              as paid. With no Essential category tagged Long-term expense there is nothing to
              spread, and the switch is replaced by a note saying so.
            </p>
            <p>
              A target is that monthly figure times the months you want covered. The roadmap
              suggests {rangeLow}–{rangeHigh} months once expensive debt is gone.
            </p>
            <p>
              <GuideTabLink tab="aside" anchor="sinking-funds">
                How spread bills count
              </GuideTabLink>
            </p>
          </ReportInfoButton>
          <div className="flex-row ms-auto">
            <ReportRangeSelect />
            <ReportExportButton
              reportId="essentials"
              getRows={() => [
                { metric: 'essentials_monthly', value: headline },
                { metric: 'essentials_as_paid', value: data.essentials.as_paid },
                { metric: 'essentials_spread', value: data.essentials.spread },
                ...data.reserve.map((r) => ({
                  metric: `reserve_${r.months}mo`,
                  value: r.amount,
                })),
                ...data.categories.map((c) => ({
                  metric: `avg_${c.name}`,
                  value: c.monthly_average,
                })),
              ]}
              captureRef={captureRef}
              window={{ start: data.window_start, end: data.window_end }}
            />
          </div>
        </ReportHeader>

        {data.tagged && (
          <SpreadSinkingFundsToggle
            budgetId={budgetId}
            longTermEssentials={data.long_term_essentials}
          />
        )}

        {!data.tagged ? (
          <div className="essentials-report__empty">
            <p>
              Nothing is tagged <strong>Essential</strong> yet. Tag a category in its inspector on
              the Budget page and this report — the Overview card and the Guide’s emergency-fund
              target with it — narrows to what a lean month actually costs.
            </p>
          </div>
        ) : (
          <div ref={captureRef}>
            {/* Tagged Essential and still not counted. The mortgage case is
                counted now; a category tagged Essential and Savings set to
                sent out is not, and silence there would be the same bug in a new class. */}
            <ReportNotes report={data} toggleAvailable={false} counts="a cost of living" />
            <MetricRow>
              <MetricCard
                label="Essentials / month"
                value={formatMoney(headline)}
                sub={
                  <>
                    {headlineMonths} average
                    {other && <span className="essentials-report__sub-line">{other}</span>}
                  </>
                }
              />
              <MetricCard
                label="Saved so far"
                value={formatMoneyOrDash(data.emergency_fund.total)}
                sub={fundCoverLine(data.fund_runway)}
                accent={data.fund_runway.months !== null && data.fund_runway.months >= rangeLow}
              />
              {worst && (
                <MetricCard
                  label="Worst month"
                  value={formatMoney(worst.total)}
                  sub={
                    worstOver === null
                      ? `${formatMonthShort(worst.month)} · no month ran over the headline`
                      : `${formatMonthShort(worst.month)} · ${worstOver}% over the headline`
                  }
                />
              )}
            </MetricRow>
            {/* The reserve sizes on one line rather than four cards: they are
                the headline times a count, and four cards of arithmetic
                crowded out the three figures that are not. */}
            <p className="essentials-report__targets">
              <span className="essentials-report__targets-label">Targets</span>
              {data.reserve.map((r, i) => {
                const inRange = r.months >= rangeLow && r.months <= rangeHigh
                return (
                  <span
                    key={r.months}
                    className={inRange ? 'essentials-report__target--range' : undefined}
                  >
                    {i > 0 && ' · '}
                    {r.months} {r.months === 1 ? 'month' : 'months'}{' '}
                    <span className="tabular">{formatMoney(r.amount)}</span>
                  </span>
                )
              })}
              <span className="essentials-report__targets-note">
                {' '}
                — the roadmap suggests {rangeLow}–{rangeHigh}
              </span>
            </p>
            <div className="essentials-report__note">
              <EmergencyFundCounting budgetId={budgetId} />
            </div>
            <p className="essentials-report__note">
              “Saved so far” is the emergency fund; the rest are targets, not balances. The{' '}
              <Link to="/guide">roadmap</Link> tracks progress against them.
            </p>

            {/* Two windows on one screen, deliberately (see
                essentials_summary's docstring): the headline is the Guide's
                last three complete months; the table averages the picker's.
                Two different "per month" figures with no explanation read as
                a bug, so the gap is said here rather than only in the info
                panel. */}
            <p className="essentials-report__note">
              Every category tagged <strong>Essential</strong> is listed, including any with no
              spending in this window — those read zero rather than going missing.
            </p>

            <p className="essentials-report__note">
              The table averages the last <strong>{averagedMonths}</strong> (
              {formatMoney(data.monthly_total_average)}/mo); the headline averages {headlineMonths}
              {spreading ? ', with yearly bills spread over 12 months' : ''}. The two differ when
              recent spending has shifted.
            </p>

            <div className="essentials-report__table-wrap">
              <table className="essentials-report__table">
                <thead>
                  <tr>
                    <th scope="col">Category</th>
                    <th scope="col" className="essentials-report__num">
                      Avg / month
                    </th>
                    <th scope="col" className="essentials-report__bar-col">
                      Share of a lean month
                    </th>
                    <th scope="col" className="essentials-report__num">
                      Total
                    </th>
                    <th scope="col" className="essentials-report__num">
                      Months
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((c) => {
                    const avg = c.monthly_average
                    // Share of the lean-month total, not of the largest
                    // category: the old max-scaled bar only restated "this
                    // is the biggest number" beside the number itself.
                    const share = shareOfLeanMonth(avg, data.monthly_total_average)
                    // Tagged Essential and not spent in this window. It is
                    // listed rather than dropped — absence is what made the
                    // report look capped at five — but it is not competing for
                    // attention with the things that cost money.
                    const quiet = c.total === 0
                    return (
                      <tr
                        key={c.category_id ?? 'uncategorized'}
                        className={quiet ? 'essentials-report__row--quiet' : undefined}
                      >
                        <td>
                          <span className="essentials-report__name">{c.name}</span>
                          {c.group_name && (
                            <span className="essentials-report__group">{c.group_name}</span>
                          )}
                        </td>
                        <td className="essentials-report__num tabular">{formatMoney(avg)}</td>
                        <td className="essentials-report__bar-col">
                          <div
                            className="essentials-report__share"
                            title={`${c.name}: ${share.toFixed(1)}% of a lean month`}
                          >
                            <div className="essentials-report__bar">
                              <div
                                className="essentials-report__bar-fill"
                                style={{ width: `${Math.min(share, 100)}%` }}
                              />
                            </div>
                            <span className="essentials-report__share-pct tabular">
                              {share.toFixed(0)}%
                            </span>
                          </div>
                        </td>
                        <td className="essentials-report__num tabular">{formatMoney(c.total)}</td>
                        <td className="essentials-report__num tabular">
                          {c.months_with_spend}/{averaged}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row">All essentials</th>
                    <td className="essentials-report__num tabular">
                      {formatMoney(data.monthly_total_average)}
                    </td>
                    <td />
                    <td className="essentials-report__num tabular">
                      {formatMoney(columnTotal(data.categories))}
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* The reserve is headline × N, so the question this chart
                answers is whether the headline is representative: each
                complete month, as paid, against a labelled line at the headline.
                A month towering over the line is the stress case the
                reserve has to survive — the Worst month card names it. */}
            <div className="essentials-report__chart">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={monthData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--border-color)"
                    vertical={false}
                  />
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
                    cursor={{ fill: 'var(--row-hover-bg)' }}
                  />
                  <ReferenceLine
                    y={headline}
                    stroke={COLOR_NET}
                    strokeDasharray="6 3"
                    label={{
                      value: `Essentials / month: ${formatMoney(headline)}`,
                      position: 'insideTopRight',
                      fill: 'var(--text-secondary)',
                      fontSize: 11,
                    }}
                  />
                  <Bar dataKey="Spent" fill={CHART_COLORS[0]} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <p className="essentials-report__chart-key">
                Bars: each complete month as paid. Dashed line: the headline, the average of{' '}
                {headlineMonths}
                {spreading ? ' with yearly bills spread' : ''}.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
