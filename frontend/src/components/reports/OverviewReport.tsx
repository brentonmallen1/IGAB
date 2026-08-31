import { useRef } from 'react'
import toast from 'react-hot-toast'
import { downloadAuthed, exportFilename } from '../../utils/exportFile'
import { useAppStore } from '../../stores/appStore'
import { useReportStore } from '../../stores/reportStore'
import { exportTransactionsPath, useDashboardMetrics } from '../../api/reports'
import { useBudgetMonth } from '../../api/budgets'
import { MetricCard } from './MetricCard'
import { ReportInfoButton, ReportScopeNote } from './ReportInfoButton'
import { ReportExportButton } from './ReportExportButton/ReportExportButton'
import { useFormatters } from '../../hooks/useFormatters'
import { ReportErrorState } from './ReportErrorState'
import {
  clampedSavingsRate,
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

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (isError) return <ReportErrorState error={error} onRetry={() => refetch()} />
  if (!data) return <div className="reports-empty">No data available.</div>

  const netWorthDeltaPct = netWorthDelta(Number(data.net_worth), Number(data.net_worth_prev))
  const spendingDeltaPct = spendingDelta(
    Number(data.expenses_this_month),
    Number(data.expenses_prev_month)
  )
  const savingsRate = clampedSavingsRate(data.savings_rate)
  const daysUntilZero = roundedDaysUntilZero(data.days_until_zero)
  const sixMonthReserve = essentialsReserve(data.essentials_monthly, 6)

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
              <strong>Essentials</strong>: the same 90-day average, counting only categories and
              payees tagged Essential — what a lean month costs, and the figure the Guide’s
              emergency-fund target is built from. Shows “—” until something is tagged.{' '}
              <strong>Savings Rate</strong>: Savings ÷ Income — money moved into savings or
              investments, not simply money left over. Shows “—” for a window with no income.{' '}
              <strong>Days Until Zero</strong>: current net worth ÷ daily burn rate — how long your
              money would last at this pace.
            </p>
            <ReportScopeNote scope="overview" />
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
                  ? [{ metric: 'to_be_assigned', value: Number(budgetMonth.to_be_assigned) }]
                  : []),
                { metric: 'net_worth', value: Number(data.net_worth) },
                { metric: 'burn_rate_30', value: Number(data.burn_rate_30) },
                { metric: 'burn_rate_90', value: Number(data.burn_rate_90) },
                ...(data.essentials_monthly != null
                  ? [{ metric: 'essentials_monthly', value: Number(data.essentials_monthly) }]
                  : []),
                ...(savingsRate !== null
                  ? [{ metric: 'savings_rate_pct', value: savingsRate }]
                  : []),
                ...(daysUntilZero !== null
                  ? [{ metric: 'days_until_zero', value: daysUntilZero }]
                  : []),
                { metric: 'income_this_period', value: Number(data.income_this_month) },
                { metric: 'spent_this_period', value: Number(data.expenses_this_month) },
              ]}
              captureRef={captureRef}
              window={{ start: filters.startDate, end: filters.endDate }}
            />
          </div>
        </div>
        <div className="overview-report__metrics-grid" ref={captureRef}>
          {budgetMonth && (
            <MetricCard
              label="To Be Assigned"
              value={formatMoney(Number(budgetMonth.to_be_assigned))}
              accent={Number(budgetMonth.to_be_assigned) !== 0}
            />
          )}
          <MetricCard
            label="Net Worth"
            value={formatMoney(Number(data.net_worth))}
            delta={
              Number(data.net_worth_prev) !== 0
                ? { value: netWorthDeltaPct, label: 'vs prior period' }
                : undefined
            }
          />
          <MetricCard
            label="30-Day Burn Rate"
            value={formatMoney(Number(data.burn_rate_30))}
            sub={`90-day avg: ${formatMoney(Number(data.burn_rate_90))}`}
          />
          <MetricCard
            label="Essentials / month"
            value={
              data.essentials_monthly != null ? formatMoney(Number(data.essentials_monthly)) : '—'
            }
            sub={
              sixMonthReserve != null
                ? `6-month reserve: ${formatMoney(sixMonthReserve)}`
                : 'Tag categories or payees Essential'
            }
          />
          <MetricCard
            label="Savings Rate"
            // "—" rather than 0%: with no income recorded there is nothing to
            // take a percentage of, and 0% reads as "saved nothing".
            value={savingsRate === null ? '—' : `${savingsRate.toFixed(1)}%`}
            sub={savingsRate === null ? 'No income recorded' : 'Savings / Income'}
          />
          {daysUntilZero !== null && (
            <MetricCard
              label="Days Until Zero"
              value={`${daysUntilZero}d`}
              sub="At current 30-day burn"
            />
          )}
          <MetricCard
            label="Income This Period"
            value={formatMoney(Number(data.income_this_month))}
          />
          <MetricCard
            label="Spent This Period"
            value={formatMoney(Number(data.expenses_this_month))}
            delta={
              Number(data.expenses_prev_month) > 0
                ? { value: spendingDeltaPct, label: 'vs prior period' }
                : undefined
            }
          />
        </div>
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
                <span className="overview-report__top-amount">{formatMoney(Number(c.total))}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
