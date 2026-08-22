import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { useCategories, useCategoryGroups } from '../../api/categories'
import {
  useCreateLiabilitySnapshot,
  useLiabilityAmortization,
  useLiabilities,
  useLinkCategoryLiability,
} from '../../api/liabilities'
import { useCreateTransaction } from '../../api/transactions'
import { AmortizationTable } from '../../components/liabilities/AmortizationTable'
import { LiabilitySettingsModal } from '../../components/liabilities/LiabilitySettingsModal'
import { PaydownChart } from '../../components/liabilities/PaydownChart'
import { PayoffPill } from '../../components/liabilities/PayoffPill'
import { Combobox } from '../../components/common/Combobox/Combobox'
import { MetricCard } from '../../components/reports/MetricCard'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import './LiabilityPage.css'

const TYPE_LABELS: Record<string, string> = {
  mortgage: 'Mortgage',
  auto: 'Auto loan',
  student: 'Student loan',
  personal: 'Personal loan',
  credit_card: 'Credit card',
  medical: 'Medical',
  other: 'Other',
}

export function LiabilityPage() {
  const { formatMoney, formatMonth } = useFormatters()
  const { liabilityId } = useParams<{ liabilityId: string }>()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  const { data: liabilities = [], isLoading } = useLiabilities(budgetId)
  const liability = liabilities.find((d) => d.id === liabilityId) ?? null

  const { isLiabilityEditorOpen, editingLiabilityId, openLiabilityEditor, closeLiabilityEditor } = useUIStore()

  const [chartMode, setChartMode] = useState<'now' | 'beginning'>('now')
  const [extraInput, setExtraInput] = useState('')
  const [extraPayment, setExtraPayment] = useState(0)
  const [showBalanceForm, setShowBalanceForm] = useState(false)
  const [newBalance, setNewBalance] = useState('')
  const [balanceDate, setBalanceDate] = useState('')
  const [showLinkPicker, setShowLinkPicker] = useState(false)

  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const createSnapshot = useCreateLiabilitySnapshot(budgetId)
  const linkCategory = useLinkCategoryLiability(budgetId)
  const createTransaction = useCreateTransaction(budgetId ?? '')

  // Debounce the what-if input so typing doesn't spam the API
  useEffect(() => {
    const handle = setTimeout(() => {
      const parsed = parseFloat(extraInput)
      setExtraPayment(!isNaN(parsed) && parsed > 0 ? parsed : 0)
    }, 400)
    return () => clearTimeout(handle)
  }, [extraInput])

  const { data: amortization } = useLiabilityAmortization(budgetId, liabilityId ?? null, {
    extraPayment,
    fromOrigination: chartMode === 'beginning',
  })

  if (!budgetId || !liabilityId) return null
  if (isLoading) {
    return <div className="liability-page"><div className="liability-page__empty">Loading…</div></div>
  }
  if (!liability) {
    return (
      <div className="liability-page">
        <div className="liability-page__empty">
          This liability doesn't exist anymore. <Link to="/liabilities">Back to liabilities</Link>
        </div>
      </div>
    )
  }

  const linkedCategory = categories.find((c) => c.id === liability.linked_category_id) ?? null
  const systemGroupIds = new Set(groups.filter((g) => g.is_system).map((g) => g.id))
  const linkableCategories = categories.filter(
    (c) =>
      !c.is_hidden &&
      !systemGroupIds.has(c.category_group_id) &&
      !c.linked_account_id
  )

  // Unknown, not zero. With no terms on file the schedule is empty, and an
  // empty schedule counted as months would read "0 months remaining" — paid
  // off — which is the opposite of what is true.
  const monthsRemaining =
    !amortization || !amortization.terms_complete || amortization.baseline_never_pays_off
      ? null
      : amortization.baseline_schedule.length

  async function handleSaveBalance(e: React.FormEvent) {
    e.preventDefault()
    const parsed = parseFloat(newBalance)
    if (isNaN(parsed) || parsed < 0) return
    await createSnapshot.mutateAsync({
      liabilityId: liability!.id,
      balance: parsed,
      ...(balanceDate ? { date: balanceDate } : {}),
    })
    toast.success('Balance updated')
    setShowBalanceForm(false)
    setNewBalance('')
    setBalanceDate('')
  }

  async function handleSeedOpeningBalance() {
    if (!liability?.linked_account_id) return
    try {
      await createTransaction.mutateAsync({
        account_id: liability.linked_account_id,
        date: liability.origination_date ?? new Date().toISOString().slice(0, 10),
        amount: -Number(liability.current_balance),
        payee_name: 'Starting Balance',
        memo: `Opening balance for ${liability.name}`,
        cleared: 'cleared',
      })
      toast.success('Opening balance added — payments now track from the register')
    } catch {
      toast.error('Failed to add the opening balance')
    }
  }

  async function handleLinkCategory(categoryId: string | null) {
    if (!categoryId) return
    await linkCategory.mutateAsync({ categoryId, liabilityId: liability!.id })
    const name = categories.find((c) => c.id === categoryId)?.name
    toast.success(`Payments now tracked from ${name ?? 'category'}`)
    setShowLinkPicker(false)
  }

  async function handleUnlinkCategory() {
    if (!linkedCategory) return
    await linkCategory.mutateAsync({ categoryId: linkedCategory.id, liabilityId: null })
    toast.success('Category unlinked')
  }

  // "Sooner" and "saved" are both differences against the contractual
  // baseline, so neither exists without terms to form one.
  const whatIfSavings =
    amortization?.terms_complete &&
    amortization.extra_schedule &&
    !amortization.extra_never_pays_off &&
    extraPayment > 0
      ? {
          monthsSooner: amortization.baseline_never_pays_off
            ? null
            : amortization.baseline_schedule.length - amortization.extra_schedule.length,
          interestSaved:
            (amortization.baseline_total_interest ?? 0) - (amortization.extra_total_interest ?? 0),
        }
      : null

  return (
    <div className="liability-page">
      <div className="liability-page__header">
        <div className="liability-page__header-left">
          <h1 className="liability-page__name">{liability.name}</h1>
          <span className="liability-page__badge">{TYPE_LABELS[liability.liability_type] ?? 'Other'}</span>
          <span className="liability-page__badge liability-page__badge--muted">
            {liability.mode === 'managed' ? 'Managed' : 'Unmanaged'}
          </span>
          <button
            className="liability-page__settings"
            onClick={() => openLiabilityEditor(liability.id)}
            aria-label="Liability settings"
            title="Liability settings"
          >
            <Settings size={14} />
          </button>
        </div>
        <div className="liability-page__header-actions">
          {liability.mode === 'managed' && liability.linked_account_id && (
            <Link className="liability-page__link" to={`/accounts/${liability.linked_account_id}`}>
              View account register
            </Link>
          )}
          {liability.mode === 'unmanaged' && (
            <button className="liability-page__action" onClick={() => setShowBalanceForm(true)}>
              Update balance
            </button>
          )}
        </div>
      </div>

      <div className="liability-page__pill-row">
        <PayoffPill liability={liability} />
      </div>

      {liability.balance_source === 'manual_fallback' && (
        <div className="liability-page__hint liability-page__hint--warning">
          <span>
            The linked account's register is empty, so the balance shown is your last manual
            entry. Add an opening balance so payments and payoff dates track from real
            transactions.
          </span>
          <button
            className="liability-page__action"
            onClick={handleSeedOpeningBalance}
            disabled={createTransaction.isPending}
          >
            {createTransaction.isPending
              ? 'Adding…'
              : `Add ${formatMoney(-Number(liability.current_balance))} opening balance`}
          </button>
        </div>
      )}

      {liability.promo_projection && liability.promo_end_date && (
        liability.promo_projection.clears_before_promo ? (
          <div className="liability-page__hint liability-page__hint--success">
            <span>
              On pace to clear this before the promo ends ({formatMonth(liability.promo_end_date)})
              {liability.promo_deferred_interest ? ' — no deferred interest' : ''}.
            </span>
          </div>
        ) : (
          <div className="liability-page__hint liability-page__hint--warning">
            <span>
              Promo ends {formatMonth(liability.promo_end_date)}. At your current pace, about{' '}
              {formatMoney(
                Number(
                  liability.promo_projection.balance_at_promo_end_live ??
                    liability.promo_projection.balance_at_promo_end_minimum
                )
              )}{' '}
              would remain
              {liability.promo_projection.deferred_interest_estimate !== null
                ? ` and ~${formatMoney(Number(liability.promo_projection.deferred_interest_estimate))} of deferred interest could be charged retroactively`
                : ` and the ${Number(liability.interest_rate)}% rate starts`}
              .
            </span>
          </div>
        )
      )}

      {liability.implied_never_pays_off === true && (
        <div className="liability-page__hint liability-page__hint--warning">
          <span>
            The {formatMoney(Number(liability.minimum_payment))} minimum payment couldn't have
            amortized the original {formatMoney(Number(liability.original_principal ?? 0))} loan
            at {Number(liability.interest_rate)}% — if your real payment includes escrow or
            insurance, enter just the principal + interest portion for accurate projections.
          </span>
        </div>
      )}

      <div className="liability-page__metrics">
        <MetricCard
          label="Current Balance"
          value={formatMoney(Number(liability.current_balance))}
          accent
        />
        {/* 0% is a real rate here — promo cards have one — so an unset rate
            has to read differently from zero, not as Number(null). */}
        <MetricCard
          label="Interest Rate"
          value={liability.interest_rate === null ? 'Not set' : `${Number(liability.interest_rate)}%`}
          sub={liability.interest_rate === null ? 'Add it for a payoff date' : undefined}
        />
        <MetricCard
          label="Interest Remaining"
          value={
            !amortization
              ? '…'
              : !amortization.terms_complete || amortization.baseline_never_pays_off
                ? '—'
                : formatMoney(Number(amortization.baseline_total_interest))
          }
          sub={
            amortization && !amortization.terms_complete
              ? 'Needs APR and minimum payment'
              : amortization?.baseline_never_pays_off
                ? "Minimum doesn't cover interest"
                : 'At minimum payment'
          }
        />
        <MetricCard
          label="Months Remaining"
          value={monthsRemaining === null ? '—' : String(monthsRemaining)}
          sub="At minimum payment"
        />
      </div>

      {liability.origination_date !== null &&
        liability.original_principal !== null &&
        Number(liability.original_principal) > 0 && (
          <div className="liability-page__progress">
            <div className="liability-page__progress-labels">
              <span>
                Originated {formatMonth(liability.origination_date)}
                {(liability.term_months ?? liability.implied_term_months) !== null
                  ? ` · ~${Math.round(
                      (liability.term_months ?? liability.implied_term_months)! / 12
                    )}-year loan`
                  : ''}
              </span>
              <span>
                {formatMoney(
                  Math.max(
                    0,
                    Number(liability.original_principal) - Number(liability.current_balance)
                  )
                )}{' '}
                of {formatMoney(Number(liability.original_principal))} paid down
              </span>
            </div>
            <div className="liability-page__progress-track">
              <div
                className="liability-page__progress-fill"
                style={{
                  width: `${Math.min(
                    100,
                    Math.max(
                      0,
                      (1 -
                        Number(liability.current_balance) /
                          Number(liability.original_principal)) *
                        100
                    )
                  )}%`,
                }}
              />
            </div>
          </div>
        )}

      {liability.mode === 'unmanaged' && !linkedCategory && (
        <div className="liability-page__hint">
          {showLinkPicker ? (
            <div className="liability-page__link-picker">
              <span>Track payments from:</span>
              <Combobox
                value={null}
                options={linkableCategories.map((c) => ({ id: c.id, label: c.name }))}
                onChange={handleLinkCategory}
                placeholder="Choose a category…"
                autoFocus
                aria-label="Category to track payments from"
              />
              <button className="liability-page__hint-dismiss" onClick={() => setShowLinkPicker(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <>
              <span>
                Link a budget category to track real payments — its spending becomes this
                liability's payment history.
              </span>
              <button className="liability-page__action" onClick={() => setShowLinkPicker(true)}>
                Link a category
              </button>
            </>
          )}
        </div>
      )}
      {linkedCategory && (
        <div className="liability-page__hint liability-page__hint--linked">
          <span>
            Payments tracked from <strong>{linkedCategory.name}</strong>
          </span>
          <button className="liability-page__hint-dismiss" onClick={handleUnlinkCategory}>
            Unlink
          </button>
        </div>
      )}

      <div className="liability-page__section">
        <div className="liability-page__section-header">
          <h2>Paydown</h2>
          <div className="liability-page__chart-controls">
            <div className="liability-page__toggle">
              <button
                className={chartMode === 'now' ? 'active' : ''}
                onClick={() => setChartMode('now')}
              >
                Now
              </button>
              <button
                className={chartMode === 'beginning' ? 'active' : ''}
                onClick={() => setChartMode('beginning')}
              >
                Beginning
              </button>
            </div>
            <label className="liability-page__whatif">
              <span>Extra monthly:</span>
              <input
                type="number"
                min="0"
                step="10"
                inputMode="decimal"
                placeholder="0"
                value={extraInput}
                onChange={(e) => setExtraInput(e.target.value)}
              />
            </label>
          </div>
        </div>
        {whatIfSavings && (
          <div className="liability-page__whatif-result">
            +{formatMoney(extraPayment)}/mo →{' '}
            {whatIfSavings.monthsSooner !== null
              ? `paid off ${whatIfSavings.monthsSooner} month${whatIfSavings.monthsSooner === 1 ? '' : 's'} sooner`
              : 'actually pays off'}
            {' · '}
            {formatMoney(Number(whatIfSavings.interestSaved))} interest saved
          </div>
        )}
        {amortization ? (
          Number(liability.current_balance) === 0 ? (
            <div className="liability-page__empty">Nothing left to pay down.</div>
          ) : (
            <PaydownChart amortization={amortization} mode={chartMode} isMobile={isMobile} />
          )
        ) : (
          <div className="liability-page__empty">Loading chart…</div>
        )}
      </div>

      <div className="liability-page__section">
        <div className="liability-page__section-header">
          <h2>Amortization schedule</h2>
          <span className="liability-page__section-sub">At the minimum payment</span>
        </div>
        {amortization ? (
          !amortization.terms_complete ? (
            <div className="liability-page__empty">
              Add this liability's APR and minimum payment to see its schedule.
            </div>
          ) : amortization.baseline_never_pays_off &&
            amortization.baseline_schedule.length === 0 ? (
            <div className="liability-page__empty">
              The minimum payment doesn't cover interest — there is no schedule to show.
            </div>
          ) : (
            <AmortizationTable schedule={amortization.baseline_schedule} />
          )
        ) : (
          <div className="liability-page__empty">Loading schedule…</div>
        )}
      </div>

      {showBalanceForm && (
        <div
          className="liability-page__balance-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowBalanceForm(false)
          }}
        >
          <form className="liability-page__balance-form" onSubmit={handleSaveBalance}>
            <h3>Update balance</h3>
            <label>
              <span>Balance owed</span>
              <input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={newBalance}
                onChange={(e) => setNewBalance(e.target.value)}
                autoFocus
                placeholder={String(liability.current_balance)}
              />
            </label>
            <label>
              <span>As of (optional — defaults to today)</span>
              <input type="date" value={balanceDate} onChange={(e) => setBalanceDate(e.target.value)} />
            </label>
            <div className="liability-page__balance-actions">
              <button type="button" onClick={() => setShowBalanceForm(false)}>
                Cancel
              </button>
              <button type="submit" className="primary" disabled={createSnapshot.isPending}>
                {createSnapshot.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLiabilityEditorOpen && editingLiabilityId === liability.id && (
        <LiabilitySettingsModal
          budgetId={budgetId}
          liability={liability}
          onClose={closeLiabilityEditor}
          onDeleted={() => navigate('/liabilities')}
        />
      )}
    </div>
  )
}
