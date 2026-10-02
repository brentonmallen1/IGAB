import { Zap } from 'lucide-react'
import { useCategoryHistoryBatch, useAutoAssign } from '../../../api/categoryHistory'
import { useAppStore } from '../../../stores/appStore'
import { useFormatters } from '../../../hooks/useFormatters'
import type { AutoAssignAction } from '../../../types'
import { useBudgetMonth } from '../../../api/budgets'
import { autoAssignRows } from './autoAssignActions'

interface Props {
  categoryIds: string[]
  budgetId: string
}

export function AutoAssignSection({ categoryIds, budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const month = useAppStore((s) => s.selectedMonth)
  const { data: histories } = useCategoryHistoryBatch(budgetId, categoryIds)
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const autoAssign = useAutoAssign(budgetId, month)

  const actions = autoAssignRows(categoryIds, histories, budgetMonth?.category_balances)

  function handleAction(action: AutoAssignAction) {
    autoAssign.mutate({ categoryIds, action })
  }

  return (
    <div className="inspector-section">
      <div className="inspector-section__header">
        <Zap size={13} />
        <span className="inspector-section__title">Auto-Assign</span>
      </div>
      <div className="inspector-autoassign">
        {actions.map(({ action, label, value }) => (
          <button
            key={action}
            className="inspector-autoassign__btn"
            onClick={() => handleAction(action)}
            disabled={autoAssign.isPending}
          >
            <span className="inspector-autoassign__label">{label}</span>
            <span className="inspector-autoassign__value tabular">{formatMoney(value)}</span>
          </button>
        ))}
        <div className="inspector-autoassign__divider" />
        <button
          className="inspector-autoassign__btn"
          onClick={() => handleAction('reset')}
          disabled={autoAssign.isPending}
        >
          <span className="inspector-autoassign__label">Reset Assigned Amount</span>
          <span className="inspector-autoassign__value tabular">{formatMoney(0)}</span>
        </button>
      </div>
    </div>
  )
}
