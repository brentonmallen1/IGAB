import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Link2, PenLine, Plus } from 'lucide-react'
import { useAccounts } from '../../api/accounts'
import { useLiabilities } from '../../api/liabilities'
import {
  LiabilitySettingsModal,
  type LiabilityPrefill,
} from '../../components/liabilities/LiabilitySettingsModal'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import './LiabilitiesOverviewPage.css'

const TYPE_LABELS: Record<string, string> = {
  mortgage: 'Mortgage',
  auto: 'Auto loan',
  student: 'Student loan',
  personal: 'Personal',
  credit_card: 'Credit card',
  medical: 'Medical',
  other: 'Other',
}

export function LiabilitiesOverviewPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const navigate = useNavigate()
  const { formatMoney, formatMonth } = useFormatters()
  const { data: liabilities = [], isLoading } = useLiabilities(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)
  const { isLiabilityEditorOpen, editingLiabilityId, openLiabilityEditor, closeLiabilityEditor } =
    useUIStore()

  const [prefill, setPrefill] = useState<LiabilityPrefill | undefined>()

  if (!budgetId) return null

  const editingLiability = liabilities.find((d) => d.id === editingLiabilityId) ?? null
  const totalOwed = liabilities.reduce((sum, d) => sum + Number(d.current_balance), 0)

  // Accounts that could be liabilities but aren't tracked yet
  const linkedAccountIds = new Set(liabilities.map((l) => l.linked_account_id).filter(Boolean))
  const suggestedAccounts = accounts.filter(
    (a) => (a.account_type === 'loan' || a.account_type === 'credit_card') && !linkedAccountIds.has(a.id)
  )

  function handleSuggestTrack(account: (typeof accounts)[0]) {
    setPrefill({
      accountId: account.id,
      accountName: account.name,
      liabilityType: account.account_type === 'credit_card' ? 'credit_card' : 'auto',
    })
    openLiabilityEditor(null)
  }

  function handleClose() {
    setPrefill(undefined)
    closeLiabilityEditor()
  }

  return (
    <div className="liabilities-page">
      <div className="liabilities-page__header">
        <div>
          <h1 className="liabilities-page__title">Liabilities</h1>
          {liabilities.length > 0 && (
            <div className="liabilities-page__total">
              {formatMoney(totalOwed)} owed across {liabilities.length} liabilit
              {liabilities.length !== 1 ? 'ies' : 'y'}
            </div>
          )}
        </div>
        <button className="liabilities-page__add" onClick={() => openLiabilityEditor(null)}>
          <Plus size={14} />
          Track a liability
        </button>
      </div>

      {isLoading ? (
        <div className="liabilities-page__empty">Loading…</div>
      ) : liabilities.length === 0 ? (
        <div className="liabilities-page__empty">
          <p>No liabilities tracked yet.</p>
          <p className="liabilities-page__empty-sub">
            Track a loan account you already have here, or a liability that lives entirely outside
            this budget — either way you get a payoff date, schedule, and paydown chart.
          </p>
          <button className="liabilities-page__add" onClick={() => openLiabilityEditor(null)}>
            <Plus size={14} />
            Track a liability
          </button>
        </div>
      ) : (
        <div className="liabilities-page__grid">
          {liabilities.map((liability) => {
            const payoffDate = liability.has_live_projection
              ? liability.live_payoff_date
              : liability.baseline_payoff_date
            const neverPays = liability.has_live_projection
              ? liability.live_never_pays_off
              : liability.baseline_never_pays_off
            return (
              <button
                key={liability.id}
                className="liability-card"
                onClick={() => navigate(`/liabilities/${liability.id}`)}
              >
                <div className="liability-card__top">
                  <span className="liability-card__name">{liability.name}</span>
                  <span className="liability-card__type">
                    {TYPE_LABELS[liability.liability_type] ?? 'Other'}
                  </span>
                </div>
                <div className="liability-card__balance tabular">
                  {formatMoney(Number(liability.current_balance))}
                </div>
                <div className="liability-card__meta">
                  <span>{Number(liability.interest_rate)}% APR</span>
                  <span
                    className="liability-card__mode"
                    title={liability.mode === 'managed' ? 'Tracked from account' : 'Manually tracked'}
                  >
                    {liability.mode === 'managed' ? (
                      <Link2 size={12} />
                    ) : (
                      <PenLine size={12} />
                    )}
                    {liability.mode === 'managed' ? 'Linked' : 'Manual'}
                  </span>
                </div>
                <div
                  className={`liability-card__payoff ${neverPays ? 'liability-card__payoff--warning' : ''}`}
                >
                  {Number(liability.current_balance) === 0 ? (
                    'Paid off'
                  ) : neverPays ? (
                    <>
                      <AlertTriangle size={12} /> Won't pay off at current rate
                    </>
                  ) : payoffDate ? (
                    `Paid off ${formatMonth(payoffDate)}`
                  ) : (
                    'Payoff date unknown'
                  )}
                </div>
              </button>
            )
          })}
        </div>
      )}

      {suggestedAccounts.length > 0 && (
        <div className="liabilities-page__suggestions">
          <h2 className="liabilities-page__suggestions-title">From your accounts</h2>
          <p className="liabilities-page__suggestions-sub">
            These accounts could be tracked as liabilities to get payoff projections and charts.
          </p>
          <div className="liabilities-page__suggestions-list">
            {suggestedAccounts.map((account) => (
              <div key={account.id} className="liability-suggestion">
                <div className="liability-suggestion__info">
                  <span className="liability-suggestion__name">{account.name}</span>
                  <span className="liability-suggestion__balance tabular">
                    {formatMoney(Math.abs(Number(account.balance)))}
                  </span>
                </div>
                <button
                  className="liability-suggestion__track"
                  onClick={() => handleSuggestTrack(account)}
                >
                  Track
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {isLiabilityEditorOpen && (
        <LiabilitySettingsModal
          budgetId={budgetId}
          liability={editingLiability}
          onClose={handleClose}
          prefill={prefill}
        />
      )}
    </div>
  )
}
