import { useAppStore } from '../../stores/appStore'
import { useReportStore } from '../../stores/reportStore'
import { useDashboardMetrics } from '../../api/reports'
import { useBudgetMonth } from '../../api/budgets'
import { MetricCard } from './MetricCard'
import { ReportInfoButton } from './ReportInfoButton'
import { formatMoney } from '../../utils/money'
import './OverviewReport.css'

interface Props {
  budgetId: string
}

export function OverviewReport({ budgetId }: Props) {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const { filters } = useReportStore()
  const { data, isLoading } = useDashboardMetrics(budgetId, filters.startDate, filters.endDate)
  const { data: budgetMonth } = useBudgetMonth(budgetId, selectedMonth)

  if (isLoading) return <div className="report-loading">Loading…</div>
  if (!data) return <div className="reports-empty">No data available.</div>

  const netWorthDelta = Number(data.net_worth_prev) !== 0
    ? ((Number(data.net_worth) - Number(data.net_worth_prev)) / Math.abs(Number(data.net_worth_prev))) * 100
    : 0

  const spendingDelta = Number(data.expenses_prev_month) > 0
    ? ((Number(data.expenses_this_month) - Number(data.expenses_prev_month)) / Number(data.expenses_prev_month)) * 100
    : 0

  const savingsRate = Math.max(0, Number(data.savings_rate) * 100)
  const daysUntilZero = data.days_until_zero != null ? Math.round(Number(data.days_until_zero)) : null

  return (
    <div className="overview-report">
      <div className="overview-report__metrics-section">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--spacing-md)' }}>
          <h2 className="report-section__title" style={{ margin: 0 }}>Overview</h2>
          <ReportInfoButton title="Overview Dashboard">
            <p>A snapshot of your financial health at a glance. All metrics use the selected date range except burn rates, which use rolling windows from today.</p>
            <p><strong>Burn Rate</strong>: average monthly spending over the last 30 or 90 days. <strong>Savings Rate</strong>: (Income − Expenses) ÷ Income. <strong>Days Until Zero</strong>: current net worth ÷ daily burn rate — how long your money would last at this pace.</p>
          </ReportInfoButton>
        </div>
        <div className="overview-report__metrics-grid">
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
            delta={Number(data.net_worth_prev) !== 0 ? { value: netWorthDelta, label: 'vs prior period' } : undefined}
          />
          <MetricCard
            label="30-Day Burn Rate"
            value={formatMoney(Number(data.burn_rate_30))}
            sub={`90-day avg: ${formatMoney(Number(data.burn_rate_90))}`}
          />
          <MetricCard
            label="Savings Rate"
            value={`${savingsRate.toFixed(1)}%`}
            sub="(Income − Expenses) / Income"
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
            delta={Number(data.expenses_prev_month) > 0 ? { value: spendingDelta, label: 'vs prior period' } : undefined}
          />
        </div>
      </div>

      {data.top_categories.length > 0 && (
        <div className="overview-report__top">
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
