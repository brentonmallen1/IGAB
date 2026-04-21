import { useState } from 'react'
import { AlertTriangle, Wand2 } from 'lucide-react'
import { BudgetTable } from '../../components/budget/BudgetTable/BudgetTable'
import { CategoryInspector } from '../../components/budget/CategoryInspector/CategoryInspector'
import { BudgetViewModal } from '../../components/budget/BudgetViewModal/BudgetViewModal'
import { AutoAssignModal } from '../../components/budget/AutoAssignModal/AutoAssignModal'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useBudgets, useBudgetMonth, useCreateBudget } from '../../api/budgets'
import { formatMoney } from '../../utils/money'
import './BudgetPage.css'

export function BudgetPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const setBudgetId = useAppStore((s) => s.setCurrentBudgetId)
  const month = useAppStore((s) => s.selectedMonth)

  const selectedCategoryIds = useUIStore((s) => s.selectedCategoryIds)
  const isViewModalOpen = useUIStore((s) => s.isViewModalOpen)
  const editingViewId = useUIStore((s) => s.editingViewId)
  const closeViewModal = useUIStore((s) => s.closeViewModal)

  const { data: budgets } = useBudgets()
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const createBudget = useCreateBudget()

  const [newName, setNewName] = useState('')
  const [showAutoAssign, setShowAutoAssign] = useState(false)

  // Auto-select first budget if none selected
  if (!budgetId && budgets && budgets.length > 0) {
    setBudgetId(budgets[0].id)
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    const budget = await createBudget.mutateAsync({ name: newName.trim() })
    setBudgetId(budget.id)
    setNewName('')
  }

  const tba = budgetMonth?.to_be_assigned ?? 0
  const tbaClass = tba > 0 ? 'positive' : tba < 0 ? 'negative' : 'zero'

  const overspentTotal = (budgetMonth?.category_balances ?? [])
    .filter((b) => b.available < 0)
    .reduce((sum, b) => sum + Math.abs(b.available), 0)
  const overspentCount = (budgetMonth?.category_balances ?? []).filter((b) => b.available < 0).length

  if (!budgetId) {
    return (
      <div className="budget-page">
        <div className="budget-page__no-budget">
          <p>No budget yet. Create one to get started.</p>
          <form className="budget-page__create-form" onSubmit={handleCreate}>
            <input
              type="text"
              className="budget-page__create-input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Budget name…"
              autoFocus
            />
            <button type="submit" className="budget-page__create-btn">
              Create Budget
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="budget-page">
      <div className="budget-page__tba">
        <span className="budget-page__tba-label">To Be Assigned</span>
        <span className={`budget-page__tba-amount ${tbaClass}`}>{formatMoney(tba)}</span>
        <button
          className="budget-page__auto-assign-btn"
          onClick={() => setShowAutoAssign(true)}
          title="Auto-assign to targets"
        >
          <Wand2 size={13} />
          Auto-assign
        </button>
      </div>
      {overspentCount > 0 && (
        <div className="budget-page__overspent-banner">
          <AlertTriangle size={13} />
          <span>
            {overspentCount} {overspentCount === 1 ? 'category' : 'categories'} overspent
            &mdash; total {formatMoney(overspentTotal)} over budget
          </span>
        </div>
      )}
      <div className="budget-page__body">
        <div className="budget-page__table-container">
          <BudgetTable />
        </div>
        {selectedCategoryIds.size > 0 && (
          <CategoryInspector budgetId={budgetId} />
        )}
      </div>
      {isViewModalOpen && (
        <BudgetViewModal
          budgetId={budgetId}
          viewId={editingViewId}
          onClose={closeViewModal}
        />
      )}
      {showAutoAssign && (
        <AutoAssignModal
          budgetId={budgetId}
          month={month}
          onClose={() => setShowAutoAssign(false)}
        />
      )}
    </div>
  )
}
