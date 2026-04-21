import { useState } from 'react'
import { ChevronDown, Zap } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategoryHistoryBatch, useAutoAssign } from '../../../api/categoryHistory'
import { useAppStore } from '../../../stores/appStore'
import { formatMoney } from '../../../utils/money'
import type { AutoAssignAction, CategoryHistory } from '../../../types'

interface Props {
  budgetId: string
  allCategoryIds: string[]
}

function formatMonthLabel(month: string) {
  const date = new Date(month + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'long' })
}

export function MonthSummary({ budgetId, allCategoryIds }: Props) {
  const month = useAppStore((s) => s.selectedMonth)
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const { data: histories } = useCategoryHistoryBatch(budgetId, allCategoryIds)
  const autoAssign = useAutoAssign(budgetId, month)

  const [summaryOpen, setSummaryOpen] = useState(true)
  const [autoAssignOpen, setAutoAssignOpen] = useState(true)
  const [futureOpen, setFutureOpen] = useState(false)

  const monthLabel = formatMonthLabel(month)

  const totalAssigned = Number(budgetMonth?.total_assigned ?? 0)
  const totalActivity = Number(budgetMonth?.total_activity ?? 0)
  const totalAvailable = (budgetMonth?.category_balances ?? []).reduce(
    (s, b) => s + Number(b.available), 0
  )
  const leftOver = totalAvailable - totalAssigned - totalActivity

  function aggregate(field: keyof CategoryHistory) {
    if (!histories?.length) return 0
    return histories.reduce((sum, h) => sum + Number(h[field] ?? 0), 0)
  }

  const autoActions: { action: AutoAssignAction; label: string; value: number }[] = [
    { action: 'last_month_assigned', label: 'Assigned Last Month', value: aggregate('last_month_assigned') },
    { action: 'last_month_spent', label: 'Spent Last Month', value: aggregate('last_month_spent') },
    { action: 'average_assigned', label: 'Average Assigned', value: aggregate('average_assigned') },
    { action: 'average_spent', label: 'Average Spent', value: aggregate('average_spent') },
  ]

  const isDisabled = autoAssign.isPending || allCategoryIds.length === 0

  return (
    <div className="month-summary">
      {/* Monthly Summary */}
      <div className="month-summary__section">
        <button
          className="month-summary__section-header"
          onClick={() => setSummaryOpen((v) => !v)}
        >
          <span>{monthLabel}'s Summary</span>
          <ChevronDown
            size={14}
            className={`month-summary__chevron ${summaryOpen ? 'month-summary__chevron--open' : ''}`}
          />
        </button>
        {summaryOpen && (
          <div className="month-summary__section-body">
            <div className="inspector-breakdown">
              <div className="inspector-breakdown__row">
                <span>Left Over from Last Month</span>
                <span className="tabular">{formatMoney(leftOver)}</span>
              </div>
              <div className="inspector-breakdown__row">
                <span>Assigned in {monthLabel}</span>
                <span className={`tabular ${totalAssigned > 0 ? 'positive' : ''}`}>
                  {totalAssigned > 0 ? '+' : ''}{formatMoney(totalAssigned)}
                </span>
              </div>
              <div className="inspector-breakdown__row">
                <span>Activity</span>
                <span className={`tabular ${totalActivity < 0 ? 'negative' : ''}`}>
                  {formatMoney(totalActivity)}
                </span>
              </div>
              <div className="inspector-breakdown__total">
                <span>Available</span>
                <span className={`tabular ${totalAvailable < 0 ? 'negative' : totalAvailable > 0 ? 'positive' : 'zero'}`}>
                  {formatMoney(totalAvailable)}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Auto-Assign */}
      <div className="month-summary__section">
        <button
          className="month-summary__section-header"
          onClick={() => setAutoAssignOpen((v) => !v)}
        >
          <span className="month-summary__section-header-icon">
            <Zap size={13} />
            Auto-Assign
          </span>
          <ChevronDown
            size={14}
            className={`month-summary__chevron ${autoAssignOpen ? 'month-summary__chevron--open' : ''}`}
          />
        </button>
        {autoAssignOpen && (
          <div className="month-summary__section-body">
            <div className="inspector-autoassign">
              {autoActions.map(({ action, label, value }) => (
                <button
                  key={action}
                  className="inspector-autoassign__btn"
                  onClick={() => autoAssign.mutate({ categoryIds: allCategoryIds, action })}
                  disabled={isDisabled}
                >
                  <span className="inspector-autoassign__label">{label}</span>
                  <span className="inspector-autoassign__value tabular">{formatMoney(value)}</span>
                </button>
              ))}
              <div className="inspector-autoassign__divider" />
              <button
                className="inspector-autoassign__btn"
                onClick={() => autoAssign.mutate({ categoryIds: allCategoryIds, action: 'reset' })}
                disabled={isDisabled}
              >
                <span className="inspector-autoassign__label">Reset Assigned Amounts</span>
                <span className="inspector-autoassign__value tabular">{formatMoney(0)}</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Assigned in Future Months */}
      <div className="month-summary__section">
        <button
          className="month-summary__section-header"
          onClick={() => setFutureOpen((v) => !v)}
        >
          <span>Assigned in Future Months</span>
          <div className="month-summary__section-header-right">
            <span className="tabular month-summary__future-amount">{formatMoney(0)}</span>
            <ChevronDown
              size={14}
              className={`month-summary__chevron ${futureOpen ? 'month-summary__chevron--open' : ''}`}
            />
          </div>
        </button>
      </div>
    </div>
  )
}
