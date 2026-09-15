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
import { pct, ratePercent } from './charts/savingsRateView'
import {
  essentialsReserve,
  netWorthDelta,
  roundedDaysUntilZero,
  spendingDelta,
} from './overviewMetrics'
import './OverviewReport.css'

interface Props {
  budgetId: string
}

export function OverviewReport({ budgetId }: Props) {
  const { formatMoney } = useFormatters()
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

  const netWorthDeltaPct = netWorthDelta(data.net_worth, data.net_worth_prev)
  const spendingDeltaPct = spendingDelta(data.expenses_this_month, data.expenses_prev_month)
  const daysUntilZero = roundedDaysUntilZero(data.days_until_zero)
  const sixMonthReserve = essentialsReserve(data.essentials?.monthly, 6)
  const otherEssentials = otherFigureNote(data.essentials, formatMoney)
  const trend = meansTrend(data.means_months)

  return (
    <div className="overview-report">
      <div className="overview-report__metrics-section surface">
        <div className="report-section__header">
          <h2 className="report-section__title">Overview</h2>
          <ReportInfoButton title="Overview Dashboard">
            <p>
              A snapshot of your financial health at a glance. All metrics use the selected date
              range except burn rates, which use rolling windows from today.
            </p>
            <p>
              <strong>Burn Rate</strong>: average monthly spending over the last 30 or 90 days.{' '}
              <strong>Essentials</strong>: the same 90-day average, counting only categories tagged
              Essential — what a lean month costs, and the figure the Guide’s emergency-fund target
              is built from. Yearly bills in Long-term expense categories are spread over 12 months
              when that setting is on (Essentials report), and the as-paid figure is shown beside
              it. Shows “—” until something is tagged. <strong>Savings Rate</strong>: Saved ÷ Income
              — money moved into savings or investments, or held in a Savings envelope that counts
              while it’s in the budget, not simply money left over. Shows “—” for a window with no
              income. Open it to see where the savings went and where the income came from.{' '}
              <strong>Days Until Zero</strong>: cash on hand ÷ daily burn rate — how long the
              budget’s cash accounts would last at this pace. Cards, loans and tracked investments
              are out: net worth is not money you can spend next week.
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
              — their income added up against their outflows — and says whether that is up or down
              on the {MEANS_TREND_POOL_MONTHS} before. The bars show each month’s margin, with the
              same {AT_MEANS_BAND_PCT}% band. Open it for the month-by-month table.
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
                { metric: 'burn_rate_90', value: data.burn_rate_90 },
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
                ...(daysUntilZero !== null
                  ? [{ metric: 'days_until_zero', value: daysUntilZero }]
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
        </div>
        <MetricRow ref={captureRef}>
          <LivingMeansCard data={data} />
          <MeansTrendCard months={data.means_months} />
          {budgetMonth && (
            <MetricCard
              label="To Be Assigned"
              value={formatMoney(budgetMonth.to_be_assigned)}
              accent={budgetMonth.to_be_assigned !== 0}
            />
          )}
          <MetricCard
            label="Net Worth"
            value={formatMoney(data.net_worth)}
            delta={
              data.net_worth_prev !== 0
                ? { value: netWorthDeltaPct, label: 'vs prior period' }
                : undefined
            }
          />
          <MetricCard
            label="30-Day Burn Rate"
            value={formatMoney(data.burn_rate_30)}
            sub={`90-day avg: ${formatMoney(data.burn_rate_90)}`}
          />
          <MetricCard
            label="Essentials / month"
            value={data.essentials ? formatMoney(data.essentials.monthly) : '—'}
            sub={
              sixMonthReserve != null ? (
                <>
                  6-month reserve: {formatMoney(sixMonthReserve)}
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
            label="Savings Rate"
            // "—" rather than 0%: with no income recorded there is nothing to
            // take a percentage of, and 0% reads as "saved nothing".
            value={pct(data.savings_rate)}
            sub={data.savings_rate === null ? 'No income recorded' : 'Savings / Income'}
            details={{
              label: `Savings rate ${pct(data.savings_rate)}. Show what contributed`,
              onOpen: () => setSavingsOpen(true),
            }}
          />
          {daysUntilZero !== null && (
            <MetricCard
              label="Days Until Zero"
              value={`${daysUntilZero}d`}
              sub="Cash at current 30-day burn"
            />
          )}
          <MetricCard label="Income This Period" value={formatMoney(data.income_this_month)} />
          <MetricCard
            label="Spent This Period"
            value={formatMoney(data.expenses_this_month)}
            delta={
              data.expenses_prev_month > 0
                ? { value: spendingDeltaPct, label: 'vs prior period' }
                : undefined
            }
          />
        </MetricRow>
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
          <h3 className="overview-report__section-heading">Top Spending</h3>
          <div className="overview-report__top-list">
            {data.top_categories.map((c, i) => (
              <div key={c.id} className="overview-report__top-item">
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
