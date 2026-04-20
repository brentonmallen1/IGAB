import { Zap } from 'lucide-react'
import { useCategoryHistoryBatch, useAutoAssign } from '../../../api/categoryHistory'
import { useAppStore } from '../../../stores/appStore'
import { formatMoney } from '../../../utils/money'
import type { AutoAssignAction, CategoryHistory } from '../../../types'

interface Props {
  categoryIds: string[]
  budgetId: string
}

export function AutoAssignSection({ categoryIds, budgetId }: Props) {
  const month = useAppStore((s) => s.selectedMonth)
  const { data: histories } = useCategoryHistoryBatch(budgetId, categoryIds)
  const autoAssign = useAutoAssign(budgetId, month)

  function aggregate(field: keyof CategoryHistory) {
    if (!histories || histories.length === 0) return 0
    return histories.reduce((sum, h) => sum + Number(h[field] ?? 0), 0)
  }

  const actions: { action: AutoAssignAction; label: string; value: number }[] = [
    { action: 'last_month_assigned', label: 'Assigned Last Month', value: aggregate('last_month_assigned') },
    { action: 'last_month_spent', label: 'Spent Last Month', value: aggregate('last_month_spent') },
    { action: 'average_assigned', label: 'Average Assigned', value: aggregate('average_assigned') },
    { action: 'average_spent', label: 'Average Spent', value: aggregate('average_spent') },
  ]

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
