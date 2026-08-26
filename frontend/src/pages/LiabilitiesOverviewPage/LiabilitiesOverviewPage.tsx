import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Link2, PenLine, Plus } from 'lucide-react'
import { useLiabilities } from '../../api/liabilities'
import {
  LiabilitySettingsModal,
} from '../../components/liabilities/LiabilitySettingsModal'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import { useAccountTypes } from '../../api/accountTypes'
import { liabilityTypeLabel } from '../../utils/liabilityTypeLabel'
import './LiabilitiesOverviewPage.css'

export function LiabilitiesOverviewPage() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: accountTypes } = useAccountTypes(budgetId)
  const navigate = useNavigate()
  const { formatMoney, formatMonth } = useFormatters()
  const { data: liabilities = [], isLoading } = useLiabilities(budgetId)
  const activeModal = useUIStore((s) => s.activeModal)
  const openModal = useUIStore((s) => s.openModal)
  const closeModal = useUIStore((s) => s.closeModal)

  if (!budgetId) return null

  const editingLiability = liabilities.find((d) => d.id === activeModal?.editingId) ?? null
  const totalOwed = liabilities.reduce((sum, d) => sum + Number(d.current_balance), 0)

  // The "these accounts could be tracked as liabilities" panel used to live
  // here. It cannot have anything to suggest any more: every
  // liability-classified account carries a companion from the moment it is
  // created, so the set it drew from is always empty — and its copy was
  // false besides, since those accounts ARE tracked.

  function handleClose() {
    closeModal()
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
        <button className="liabilities-page__add" onClick={() => openModal('liability')}>
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
          <button className="liabilities-page__add" onClick={() => openModal('liability')}>
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
                className="liability-card surface"
                onClick={() => navigate(`/liabilities/${liability.id}`)}
              >
                <div className="liability-card__top">
                  <span className="liability-card__name">{liability.name}</span>
                  <span className="liability-card__type">
                    {liabilityTypeLabel(liability.liability_type, accountTypes)}
                  </span>
                </div>
                <div className="liability-card__balance tabular">
                  {formatMoney(Number(liability.current_balance))}
                </div>
                <div className="liability-card__meta">
                  <span>
                    {liability.interest_rate === null
                      ? 'APR not set'
                      : `${Number(liability.interest_rate)}% APR`}
                  </span>
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
                      <AlertTriangle size={12} />{' '}
                      {liability.has_live_projection
                        ? "Recent payments won't pay this off"
                        : "Minimum payment won't pay this off"}
                    </>
                  ) : !liability.terms_complete ? (
                    'Needs APR and minimum payment'
                  ) : payoffDate ? (
                    `Paid off ${formatMonth(payoffDate)}`
                  ) : (
                    'Payoff date unknown'
                  )}
                </div>
                {liability.promo_projection &&
                  !liability.promo_projection.clears_before_promo &&
                  liability.promo_end_date && (
                    <div className="liability-card__payoff liability-card__payoff--warning">
                      <AlertTriangle size={12} /> Promo ends{' '}
                      {formatMonth(liability.promo_end_date)}
                    </div>
                  )}
              </button>
            )
          })}
        </div>
      )}

      {activeModal?.kind === 'liability' && (
        <LiabilitySettingsModal
          budgetId={budgetId}
          liability={editingLiability}
          onClose={handleClose}
        />
      )}
    </div>
  )
}
