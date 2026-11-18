import { Zap } from 'lucide-react'
import { useCategoryHistoryBatch } from '../../../api/categoryHistory'
import { useAppStore } from '../../../stores/appStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { useBudgetMonth } from '../../../api/budgets'
import { useAutoAssignActions } from './useAutoAssignActions'

interface Props {
  categoryIds: string[]
  budgetId: string
}

export function AutoAssignSection({ categoryIds, budgetId }: Props) {
  const { formatMoney } = useFormatters()
  const month = useAppStore((s) => s.selectedMonth)
  const { data: histories } = useCategoryHistoryBatch(budgetId, categoryIds, month)
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const {
    rows: actions,
    press: handleAction,
    isPending,
    dialog,
  } = useAutoAssignActions(budgetId, month, categoryIds, histories, budgetMonth?.category_balances)

  return (
    <div className="inspector-section">
      <div className="inspector-section__header">
        <Zap size={13} />
        <span className="inspector-section__title">Auto-Assign</span>
      </div>
      <div className="inspector-autoassign">
        {actions.map((row) => (
          <button
            key={row.label}
            className="inspector-autoassign__btn"
            onClick={() => handleAction(row)}
            disabled={isPending}
          >
            <span className="inspector-autoassign__label">{row.label}</span>
            <span className="inspector-autoassign__value tabular">{formatMoney(row.value)}</span>
          </button>
        ))}
        <div className="inspector-autoassign__divider" />
        <button
          className="inspector-autoassign__btn"
          onClick={() => handleAction({ action: 'reset' })}
          disabled={isPending}
        >
          <span className="inspector-autoassign__label">Reset Assigned Amount</span>
          <span className="inspector-autoassign__value tabular">{formatMoney(0)}</span>
        </button>
      </div>
      {dialog}
    </div>
  )
}
