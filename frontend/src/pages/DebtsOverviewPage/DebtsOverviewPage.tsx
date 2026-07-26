import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Plus } from 'lucide-react'
import { useDebts } from '../../api/debts'
import { DebtSettingsModal } from '../../components/debts/DebtSettingsModal'
import { formatMonthYear } from '../../components/debts/PayoffPill'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { formatMoney } from '../../utils/money'
import './DebtsOverviewPage.css'

const TYPE_LABELS: Record<string, string> = {
  mortgage: 'Mortgage',
  auto: 'Auto loan',
  student: 'Student loan',
  personal: 'Personal',
  credit_card: 'Credit card',
  medical: 'Medical',
  other: 'Other',
}

export function DebtsOverviewPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const navigate = useNavigate()
  const { data: debts = [], isLoading } = useDebts(budgetId)
  const { isDebtEditorOpen, editingDebtId, openDebtEditor, closeDebtEditor } = useUIStore()

  if (!budgetId) return null

  const editingDebt = debts.find((d) => d.id === editingDebtId) ?? null
  const totalOwed = debts.reduce((sum, d) => sum + Number(d.current_balance), 0)

  return (
    <div className="debts-page">
      <div className="debts-page__header">
        <div>
          <h1 className="debts-page__title">Debts</h1>
          {debts.length > 0 && (
            <div className="debts-page__total">
              {formatMoney(totalOwed)} owed across {debts.length} debt
              {debts.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
        <button className="debts-page__add" onClick={() => openDebtEditor(null)}>
          <Plus size={14} />
          Track a debt
        </button>
      </div>

      {isLoading ? (
        <div className="debts-page__empty">Loading…</div>
      ) : debts.length === 0 ? (
        <div className="debts-page__empty">
          <p>No debts tracked yet.</p>
          <p className="debts-page__empty-sub">
            Track a loan account you already have here, or a debt that lives entirely outside
            this budget — either way you get a payoff date, schedule, and paydown chart.
          </p>
          <button className="debts-page__add" onClick={() => openDebtEditor(null)}>
            <Plus size={14} />
            Track a debt
          </button>
        </div>
      ) : (
        <div className="debts-page__grid">
          {debts.map((debt) => {
            const payoffDate = debt.has_live_projection
              ? debt.live_payoff_date
              : debt.baseline_payoff_date
            const neverPays = debt.has_live_projection
              ? debt.live_never_pays_off
              : debt.baseline_never_pays_off
            return (
              <button
                key={debt.id}
                className="debt-card"
                onClick={() => navigate(`/debts/${debt.id}`)}
              >
                <div className="debt-card__top">
                  <span className="debt-card__name">{debt.name}</span>
                  <span className="debt-card__type">{TYPE_LABELS[debt.debt_type] ?? 'Other'}</span>
                </div>
                <div className="debt-card__balance tabular">
                  {formatMoney(Number(debt.current_balance))}
                </div>
                <div className="debt-card__meta">
                  <span>{Number(debt.interest_rate)}% APR</span>
                  <span className="debt-card__mode">
                    {debt.mode === 'managed' ? 'From account' : 'Manual'}
                  </span>
                </div>
                <div className={`debt-card__payoff ${neverPays ? 'debt-card__payoff--warning' : ''}`}>
                  {Number(debt.current_balance) === 0 ? (
                    'Paid off'
                  ) : neverPays ? (
                    <>
                      <AlertTriangle size={12} /> Won't pay off at current rate
                    </>
                  ) : payoffDate ? (
                    `Paid off ${formatMonthYear(payoffDate)}`
                  ) : (
                    'Payoff date unknown'
                  )}
                </div>
              </button>
            )
          })}
        </div>
      )}

      {isDebtEditorOpen && (
        <DebtSettingsModal budgetId={budgetId} debt={editingDebt} onClose={closeDebtEditor} />
      )}
    </div>
  )
}
