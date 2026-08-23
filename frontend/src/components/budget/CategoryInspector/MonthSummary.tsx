import { sumBalances } from '../budgetTotals'
import { useState } from 'react'
import { ChevronDown, Clock, Zap } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategoryHistoryBatch, useAutoAssign } from '../../../api/categoryHistory'
import { useTargetsByBudget } from '../../../api/targets'
import { useDeleteTarget } from '../../../api/targets'
import { useAppStore } from '../../../stores/appStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { today } from '../../../utils/dates'
import { TargetEditor } from '../TargetEditor'
import type { AutoAssignAction, Category, CategoryHistory, CategoryTarget } from '../../../types'

interface Props {
  budgetId: string
  allCategoryIds: string[]
  categories: Category[]
}

function PastTargetRow({ target, categoryName, onEdit, formatMoney, formatDate }: {
  target: CategoryTarget
  categoryName: string
  onEdit: () => void
  formatMoney: (amount: number) => string
  formatDate: (dateStr: string) => string
}) {
  const deleteTarget = useDeleteTarget(target.category_id)
  return (
    <div className="past-target-row">
      <div className="past-target-row__info">
        <span className="past-target-row__name">{categoryName}</span>
        <span className="past-target-row__meta">
          {formatMoney(Number(target.target_amount))} · {target.target_date ? formatDate(target.target_date) : ''}
        </span>
      </div>
      <div className="past-target-row__actions">
        <button className="past-target-row__btn" onClick={onEdit} title="Edit target to reuse">
          Edit
        </button>
        <button
          className="past-target-row__btn past-target-row__btn--danger"
          onClick={() => deleteTarget.mutate()}
          title="Delete target"
        >
          Delete
        </button>
      </div>
    </div>
  )
}

export function MonthSummary({ budgetId, allCategoryIds, categories }: Props) {
  const { formatMoney, formatDate, formatMonth, settings } = useFormatters()
  const month = useAppStore((s) => s.selectedMonth)
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const { data: histories } = useCategoryHistoryBatch(budgetId, allCategoryIds)
  const { data: allTargets } = useTargetsByBudget(budgetId)
  const autoAssign = useAutoAssign(budgetId, month)

  const [summaryOpen, setSummaryOpen] = useState(true)
  const [autoAssignOpen, setAutoAssignOpen] = useState(true)
  const [futureOpen, setFutureOpen] = useState(false)
  const [pastTargetsOpen, setPastTargetsOpen] = useState(false)
  const [editingTarget, setEditingTarget] = useState<{ categoryId: string; categoryName: string; target: CategoryTarget } | null>(null)

  const todayStr = today()
  const categoryMap = new Map(categories.map((c) => [c.id, c]))

  const pastTargets = (allTargets ?? []).filter(
    (t) => t.target_date && t.target_date < todayStr
  )

  // Get just the month name from the full month string
  const monthLabel = formatMonth(month).split(' ')[settings.dateFormat === 'ymd' ? 1 : 0]

  // All four figures from one set of balances. This used to subtract the
  // server's total_assigned/total_activity from a client-summed available, so
  // anything the server leaves out of those totals but includes in
  // category_balances — system groups, hidden categories, credit-card payment
  // categories — landed entirely in "left over".
  const {
    assigned: totalAssigned,
    activity: totalActivity,
    available: totalAvailable,
    carriedOver: leftOver,
  } = sumBalances(budgetMonth?.category_balances ?? [])

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

      {/* Past Targets */}
      {pastTargets.length > 0 && (
        <div className="month-summary__section">
          <button
            className="month-summary__section-header"
            onClick={() => setPastTargetsOpen((v) => !v)}
          >
            <span className="month-summary__section-header-icon">
              <Clock size={13} />
              Past Targets
            </span>
            <div className="month-summary__section-header-right">
              <span className="month-summary__past-count">{pastTargets.length}</span>
              <ChevronDown
                size={14}
                className={`month-summary__chevron ${pastTargetsOpen ? 'month-summary__chevron--open' : ''}`}
              />
            </div>
          </button>
          {pastTargetsOpen && (
            <div className="month-summary__section-body">
              {pastTargets.map((t) => {
                const cat = categoryMap.get(t.category_id)
                if (!cat) return null
                return (
                  <PastTargetRow
                    key={t.id}
                    target={t}
                    categoryName={cat.name}
                    onEdit={() => setEditingTarget({ categoryId: cat.id, categoryName: cat.name, target: t })}
                    formatMoney={formatMoney}
                    formatDate={formatDate}
                  />
                )
              })}
            </div>
          )}
        </div>
      )}

      {editingTarget && (
        <TargetEditor
          categoryId={editingTarget.categoryId}
          categoryName={editingTarget.categoryName}
          existing={editingTarget.target}
          onClose={() => setEditingTarget(null)}
        />
      )}
    </div>
  )
}
