import { useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { downloadAuthed, exportFilename } from '../../utils/exportFile'
import { useAppStore } from '../../stores/appStore'
import { useReportStore } from '../../stores/reportStore'
import { exportTransactionsPath, useDashboardMetrics } from '../../api/reports'
import { useBudgetMonth } from '../../api/budgets'
import { MetricCard } from './MetricCard'
import { LivingMeansCard } from './LivingMeansCard'
import { MeansTrendCard } from './MeansTrendCard'
import { AT_MEANS_BAND_PCT, MEANS_TREND_POOL_MONTHS, meansTrend, signedMargin } from './livingMeans'
import { MetricRow } from './MetricRow'
import { ReportInfoButton, ReportScopeNote } from './ReportInfoButton'
import { ReportExportButton } from './ReportExportButton/ReportExportButton'
import { otherFigureNote } from '../../utils/essentialsFigures'
import { useFormatters } from '../../hooks/useFormatters'
import { ReportErrorState } from './ReportErrorState'
import { SavingsRateDialog } from './SavingsRateDialog'
import { rateFormula } from './savingsRateBreakdown'
import { savingsRateLabel } from '../../utils/flowLabels'
import { pct, ratePercent } from './charts/savingsRateView'
import { burnPriorLine } from './charts/burnRateView'
import { periodHeading, runwayFallback, spendingDelta } from './overviewMetrics'
import { runwayBasis, runwayStatement } from '../../utils/runway'
import { categoryKey } from './drillScope'
import { likeForLikeLine } from '../../utils/trackingStart'
import { today } from '../../utils/dates'
import { monthRange } from '../../utils/reportMonths'
import './OverviewReport.css'
import { ReportHeader } from './ReportHeader'

interface Props {
  budgetId: string
}

export function OverviewReport({ budgetId }: Props) {
  const { formatMoney, formatMonthShort, formatDayMonth, formatDate } = useFormatters()
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const { filters } = useReportStore()
  const { data, isLoading, isError, error, refetch } = useDashboardMetrics(
    budgetId,
    filters.startDate,
    filters.endDate
  )
  const { data: budgetMonth } = useBudgetMonth(budgetId, selectedMonth)
  const captureRef = useRef<HTMLDivElement>(null)
  const [savingsOpen, setSavingsOpen] = useState(false)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return <div className="reports-empty">No data available.</div>

  // Like-for-like, as the Net Worth report's headline: less what began being
  // counted since the day before the range. A percentage of net worth read
  // "+225.5%" for a range in which accounts were linked and a house first
  // valued — and a percentage of a negative or near-zero net worth says
  // nothing at all — so the card states dollars.
  const netWorthChange = likeForLikeLine(
    data.net_worth_change,
    data.net_worth_entered,
    data.net_worth - data.net_worth_prev,
    formatMoney
  )
  const spendingDeltaPct = spendingDelta(data.expenses_this_month, data.expenses_prev_month)
  const runway = runwayStatement(data.runway, formatDate)
  const runwayNote = runwayFallback(data.runway)
  const otherEssentials = otherFigureNote(data.essentials, formatMoney)
  const trend = meansTrend(data.means_months)
  const period = periodHeading(
    filters.startDate,
    filters.endDate,
    today(),
    formatMonthShort,
    formatDayMonth
  )
  const essentialsMonths = data.essentials
    ? monthRange(data.essentials.window_start, data.essentials.window_end, formatMonthShort)
    : null

  return (
    <div className="overview-report">
      <div className="overview-report__metrics-section surface">
        <ReportHeader>
          <h2 className="report-section__title">Overview</h2>
          <ReportInfoButton title="Overview Dashboard">
            <p>
              The cards come in two groups. <strong>This period</strong> follows the date range —
              the last complete month unless you pick another: <strong>Your Means</strong>,{' '}
              <strong>Savings Rate</strong>, <strong>Income</strong>, <strong>Spent</strong> and{' '}
              <strong>Top Spending</strong>. A range that runs to today is marked <em>so far</em>:
              its pay and bills are still arriving. <strong>Now</strong> does not move with the
              range: <strong>Ready to Assign</strong> is the month open on the Budget page,{' '}
              <strong>Net Worth</strong> is today’s, and its change is against the day before the
              range, like-for-like: an account linked with its balance, or a value first entered, in
              between is named beside it rather than counted as growth. <strong>Burn Rate</strong>{' '}
              ends yesterday, <strong>Runway</strong> is today’s,
              <strong> Essentials</strong> is the last three complete months, and{' '}
              <strong>Means trend</strong> the last 12 complete months.
            </p>
            <p>
              <strong>Burn Rate</strong>: spending over the 30 days to yesterday, net of refunds,
              beside the 60 days before them averaged per 30 days, and the change between the two.
              Today is left out because its transactions are rarely all in. The windows share no
              day, so a jump in recent spending shows as a change instead of being averaged into
              both; no change is shown when the prior 60 days had no spending.{' '}
              <strong>Essentials</strong>: the last three complete months averaged, counting only
              categories tagged Essential — what a lean month costs, and the figure the Guide’s
              emergency-fund target is built from. Yearly bills in Long-term expense categories are
              spread over 12 months when that setting is on (Essentials report), and the as-paid
              figure is shown beside it. Shows “—” until something is tagged.{' '}
              <strong>Savings rate</strong>: Saved ÷ Income — money moved into savings or
              investments, or held in a Savings envelope that counts while it’s in the budget, not
              simply money left over. Debt payments are not in it; the Savings Rate report can add
              them. Shows “—” for a window with no income. Open it to see where the savings went and
              where the income came from. <strong>Runway</strong>: how long your money would last if
              income stopped today — your checking and your emergency fund, with what your credit
              cards owe paid first, spent at your Essentials figure. It says the date it runs out.
              With no emergency fund chosen it counts checking alone, and with nothing tagged
              Essential it spends at all your spending; the card says which. The Cash Projection
              draws the same figure for other choices.
            </p>
            <p>
              <strong>Your Means</strong>: income against what living cost over the range — spending
              plus debt payments. Below your means is money left over; at your means is outflows
              within {AT_MEANS_BAND_PCT}% of income either side; above is outflows beyond that.
              Savings transfers are not outflows. Shows “—” when no income was recorded. Open it to
              see the figures, the biggest spending categories and the prior period.
            </p>
            <p>
              <strong>Means trend</strong>: the same reading over the last 12 complete months,
              whatever range is selected. The figure pools the last {MEANS_TREND_POOL_MONTHS} months
              — their income added up against their outflows — and the line under it says what the{' '}
              {MEANS_TREND_POOL_MONTHS} before them read. The bars show each month’s margin, with
              the same {AT_MEANS_BAND_PCT}% band. Open it for the month-by-month table.
            </p>
            <ReportScopeNote report="overview" />
          </ReportInfoButton>
          <div className="flex-row ms-auto">
            <button
              className="report-btn"
              onClick={() =>
                downloadAuthed(
                  exportTransactionsPath(budgetId, 'csv', filters.startDate, filters.endDate),
                  exportFilename('transactions', 'csv', {
                    start: filters.startDate,
                    end: filters.endDate,
                  })
                ).catch(() => toast.error('Export failed.'))
              }
            >
              Export transactions
            </button>
            <ReportExportButton
              reportId="overview"
              getRows={() => [
                ...(budgetMonth
                  ? [{ metric: 'to_be_assigned', value: budgetMonth.to_be_assigned }]
                  : []),
                { metric: 'net_worth', value: data.net_worth },
                { metric: 'burn_rate_30', value: data.burn_rate_30 },
                { metric: 'burn_rate_prior_60', value: data.burn_rate_prior_60 },
                ...(data.essentials
                  ? [
                      { metric: 'essentials_monthly', value: data.essentials.monthly },
                      { metric: 'essentials_as_paid', value: data.essentials.as_paid },
                      { metric: 'essentials_spread', value: data.essentials.spread },
                    ]
                  : []),
                ...(data.savings_rate !== null
                  ? [{ metric: 'savings_rate_pct', value: ratePercent(data.savings_rate) }]
                  : []),
                ...(data.runway.months !== null
                  ? [
                      { metric: 'runway_months', value: data.runway.months },
                      { metric: 'runway_runs_out_on', value: data.runway.runs_out_on },
                    ]
                  : []),
                { metric: 'income_this_period', value: data.income_this_month },
                { metric: 'spent_this_period', value: data.expenses_this_month },
                { metric: 'debt_payments_this_period', value: data.debt_payments_this_month },
                { metric: 'outflows_this_period', value: data.outflows_this_month },
                ...(trend.recent.margin
                  ? [
                      {
                        metric: 'means_trend_3_month_margin_pct',
                        value: signedMargin(trend.recent.margin),
                      },
                    ]
                  : []),
                { metric: 'means_trend_months_below', value: trend.belowCount },
                { metric: 'means_trend_months', value: trend.bars.length },
              ]}
              captureRef={captureRef}
              window={{ start: filters.startDate, end: filters.endDate }}
            />
          </div>
        </ReportHeader>
        <div ref={captureRef}>
          <h3 className="overview-report__section-heading">
            This period <span className="overview-report__period">· {period}</span>
          </h3>
          <MetricRow>
            <LivingMeansCard data={data} />
            <MetricCard
              label={savingsRateLabel(false)}
              // "—" rather than 0%: with no income recorded there is nothing to
              // take a percentage of, and 0% reads as "saved nothing".
              value={pct(data.savings_rate)}
              sub={data.savings_rate === null ? 'No income recorded' : rateFormula(false)}
              details={{
                label: `Savings rate ${pct(data.savings_rate)}. Show what contributed`,
                onOpen: () => setSavingsOpen(true),
              }}
            />
            <MetricCard label="Income" value={formatMoney(data.income_this_month)} />
            <MetricCard
              label="Spent"
              value={formatMoney(data.expenses_this_month)}
              delta={
                spendingDeltaPct !== null
                  ? // More spending is the bad direction: "+21%" was drawn green.
                    { value: spendingDeltaPct, label: 'vs prior period', good: 'down' }
                  : undefined
              }
            />
          </MetricRow>
          <h3 className="overview-report__section-heading overview-report__section-heading--now">
            Now
          </h3>
          <MetricRow>
            {budgetMonth && (
              <MetricCard
                label="Ready to Assign"
                value={formatMoney(budgetMonth.to_be_assigned)}
                accent={budgetMonth.to_be_assigned !== 0}
              />
            )}
            <MetricCard
              label="Net Worth"
              value={formatMoney(data.net_worth)}
              sub={
                netWorthChange && (
                  <>
                    {netWorthChange.value} like-for-like since the range began
                    {data.net_worth_entered !== 0 && (
                      <span className="overview-report__sub-line">{netWorthChange.sub}</span>
                    )}
                  </>
                )
              }
            />
            <MetricCard
              label="30-Day Burn Rate"
              value={formatMoney(data.burn_rate_30)}
              sub={burnPriorLine(data.burn_rate_30, data.burn_rate_prior_60, formatMoney)}
            />
            <MetricCard
              label="Essentials / month"
              value={data.essentials ? formatMoney(data.essentials.monthly) : '—'}
              sub={
                data.essentials ? (
                  <>
                    {essentialsMonths ? `${essentialsMonths} average` : '3-month average'}
                    {otherEssentials && (
                      <span className="overview-report__sub-line">{otherEssentials}</span>
                    )}
                  </>
                ) : (
                  'Tag categories Essential'
                )
              }
            />
            <MetricCard
              label="Runway"
              value={runway.value}
              sub={
                <>
                  {runway.detail}
                  <span className="overview-report__sub-line">
                    If income stopped: {runwayBasis(data.runway)}
                  </span>
                  {runwayNote && <span className="overview-report__sub-line">{runwayNote}</span>}
                </>
              }
              warning={runway.gone}
            />
            <MeansTrendCard months={data.means_months} />
          </MetricRow>
        </div>
        {savingsOpen && (
          <SavingsRateDialog
            budgetId={budgetId}
            startDate={filters.startDate}
            endDate={filters.endDate}
            rate={data.savings_rate}
            withDebt={false}
            onClose={() => setSavingsOpen(false)}
          />
        )}
      </div>

      {data.top_categories.length > 0 && (
        <div className="overview-report__top surface">
          <h3 className="overview-report__section-heading">
            Top Spending <span className="overview-report__period">· {period}</span>
          </h3>
          <div className="overview-report__top-list">
            {data.top_categories.map((c, i) => (
              <div key={categoryKey(c.id)} className="overview-report__top-item">
                <span className="overview-report__top-rank">{i + 1}</span>
                <div className="overview-report__top-info">
                  <span className="overview-report__top-name">{c.name}</span>
                  <span className="overview-report__top-group">{c.group_name}</span>
                </div>
                <span className="overview-report__top-amount">{formatMoney(c.total)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
