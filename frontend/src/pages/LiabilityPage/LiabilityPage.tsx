import { parseAmountInput } from '../../utils/money'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { useCategories } from '../../api/categories'
import {
  useCreateLiabilitySnapshot,
  useLiabilityAmortization,
  useUpdateLiability,
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
import { MetricRow } from '../../components/reports/MetricRow'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { useFormatters } from '../../hooks/useFormatters'
import { DatedAmountForm } from '../../components/common/DatedAmountForm/DatedAmountForm'
import { useAssets, useLinkAsset } from '../../api/assets'
import { equityOf } from '../../utils/equity'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAccountTypes } from '../../api/accountTypes'
import { liabilityTypeLabel } from '../../utils/liabilityTypeLabel'
import './LiabilityPage.css'
import { Pill } from '../../components/common/Pill/Pill'
import { Surface } from '../../components/common/Surface'

export function LiabilityPage() {
  const { formatMoney, formatMonth } = useFormatters()
  const { liabilityId } = useParams<{ liabilityId: string }>()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: accountTypes } = useAccountTypes(budgetId)
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  const { data: liabilities = [], isLoading } = useLiabilities(budgetId)
  const liability = liabilities.find((d) => d.id === liabilityId) ?? null

  const activeModal = useUIStore((s) => s.activeModal)
  const openModal = useUIStore((s) => s.openModal)
  const closeModal = useUIStore((s) => s.closeModal)

  const [chartMode, setChartMode] = useState<'now' | 'beginning'>('now')
  // null = untouched: the field shows the STORED plan, so the page opens on
  // the with-plan schedule instead of demanding the figure be retyped.
  // A string (even '') means the user is trying something else right now.
  const [extraInput, setExtraInput] = useState<string | null>(null)
  const [curtailInput, setCurtailInput] = useState('')
  const [showBalanceForm, setShowBalanceForm] = useState(false)
  const [showLinkPicker, setShowLinkPicker] = useState(false)
  const [showAssetPicker, setShowAssetPicker] = useState(false)

  const { data: categories = [] } = useCategories(budgetId)
  const { data: assets = [] } = useAssets(budgetId)
  const createSnapshot = useCreateLiabilitySnapshot(budgetId)
  const linkCategory = useLinkCategoryLiability(budgetId)
  const linkAsset = useLinkAsset(budgetId ?? '')
  const createTransaction = useCreateTransaction(budgetId ?? '')
  const updateLiability = useUpdateLiability(budgetId)

  const storedPlan = liability?.planned_extra_payment ?? null
  const effectiveExtra = extraInput ?? (storedPlan !== null ? String(storedPlan) : '')

  // Debounced so typing doesn't spam the API — the same hook the Guide's
  // calculators use.
  const settledExtra = useDebouncedValue(effectiveExtra)
  const settledCurtail = useDebouncedValue(curtailInput)
  const extraPayment = useMemo(() => {
    const parsed = parseAmountInput(settledExtra)
    return !isNaN(parsed) && parsed > 0 ? parsed : 0
  }, [settledExtra])
  const curtailment = useMemo(() => {
    const parsed = parseAmountInput(settledCurtail)
    return !isNaN(parsed) && parsed > 0 ? parsed : 0
  }, [settledCurtail])

  const { data: amortization } = useLiabilityAmortization(budgetId, liabilityId ?? null, {
    extraPayment,
    curtailment,
    fromOrigination: chartMode === 'beginning',
  })

  if (!budgetId || !liabilityId) return null
  if (isLoading) {
    return (
      <div className="liability-page">
        <div className="liability-page__empty">Loading…</div>
      </div>
    )
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
  const securedAsset = assets.find((a) => a.id === liability.linked_asset_id) ?? null
  // One home for the subtraction (utils/equity.ts) — the AssetPage renders
  // the same figure and the two must not be able to disagree.
  const assetEquity = securedAsset
    ? equityOf(securedAsset.current_value, securedAsset.id, liabilities)
    : null
  // A liability may bind a category no account and no *other* liability owns.
  // linked_liability_id was not exposed before, so this offered categories
  // another liability already held.
  const linkableCategories = categories.filter(
    (c) =>
      c.is_assignable &&
      !c.linked_account_id &&
      (!c.linked_liability_id || c.linked_liability_id === liability.id)
  )

  // Unknown, not zero. With no terms on file the schedule is empty, and an
  // empty schedule counted as months would read "0 months remaining" — paid
  // off — which is the opposite of what is true.
  const monthsRemaining =
    !amortization || !amortization.terms_complete || amortization.baseline_never_pays_off
      ? null
      : amortization.baseline_schedule.length

  async function handleLinkAsset(assetId: string | null) {
    if (!assetId) return
    await linkAsset.mutateAsync({ liabilityId: liability!.id, assetId })
    setShowAssetPicker(false)
    toast.success('Linked')
  }

  async function handleSavePlan() {
    await updateLiability.mutateAsync({
      liabilityId: liability!.id,
      planned_extra_payment: extraPayment,
    })
    setExtraInput(null) // back to following the stored plan
    toast.success(`Plan saved: +${formatMoney(extraPayment)}/mo to principal`)
  }

  async function handleClearPlan() {
    await updateLiability.mutateAsync({ liabilityId: liability!.id, planned_extra_payment: null })
    setExtraInput(null)
    toast.success('Plan cleared')
  }

  async function handleSaveBalance(balance: number, date: string | null) {
    await createSnapshot.mutateAsync({
      liabilityId: liability!.id,
      balance,
      ...(date ? { date } : {}),
    })
    toast.success('Balance updated')
    setShowBalanceForm(false)
  }

  async function handleSeedOpeningBalance() {
    if (!liability?.linked_account_id) return
    try {
      await createTransaction.mutateAsync({
        account_id: liability.linked_account_id,
        date: liability.origination_date ?? new Date().toISOString().slice(0, 10),
        amount: -liability.current_balance,
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
    (extraPayment > 0 || curtailment > 0)
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
          <Pill caps>{liabilityTypeLabel(liability.liability_type, accountTypes)}</Pill>
          <Pill caps tone="outline">
            {liability.mode === 'managed' ? 'Managed' : 'Unmanaged'}
          </Pill>
          <button
            className="liability-page__settings"
            onClick={() => openModal('liability', liability.id)}
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
            The linked account's register is empty, so the balance shown is your last manual entry.
            Add an opening balance so payments and payoff dates track from real transactions.
          </span>
          <button
            className="liability-page__action"
            onClick={handleSeedOpeningBalance}
            disabled={createTransaction.isPending}
          >
            {createTransaction.isPending
              ? 'Adding…'
              : `Add ${formatMoney(-liability.current_balance)} opening balance`}
          </button>
        </div>
      )}

      {liability.promo_projection &&
        liability.promo_end_date &&
        (liability.promo_projection.clears_before_promo ? (
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
                ? ` and ~${formatMoney(liability.promo_projection.deferred_interest_estimate)} of deferred interest could be charged retroactively`
                : ` and the ${Number(liability.interest_rate)}% rate starts`}
              .
            </span>
          </div>
        ))}

      {liability.implied_never_pays_off === true && (
        <div className="liability-page__hint liability-page__hint--warning">
          <span>
            The {formatMoney(Number(liability.minimum_payment))} minimum payment couldn't have
            amortized the original {formatMoney(Number(liability.original_principal ?? 0))} loan at{' '}
            {Number(liability.interest_rate)}% — if your real payment includes escrow or insurance,
            enter just the principal + interest portion for accurate projections.
          </span>
        </div>
      )}

      <MetricRow>
        <MetricCard
          variant="raised"
          label="Current Balance"
          value={formatMoney(liability.current_balance)}
          accent
        />
        {/* 0% is a real rate here — promo cards have one — so an unset rate
            has to read differently from zero, not as Number(null). */}
        <MetricCard
          variant="raised"
          label="Interest Rate"
          value={liability.interest_rate === null ? 'Not set' : `${liability.interest_rate}%`}
          sub={liability.interest_rate === null ? 'Add it for a payoff date' : undefined}
        />
        <MetricCard
          variant="raised"
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
          variant="raised"
          label="Months Remaining"
          value={monthsRemaining === null ? '—' : String(monthsRemaining)}
          sub="At minimum payment"
        />
      </MetricRow>

      {liability.origination_date !== null &&
        liability.original_principal !== null &&
        liability.original_principal > 0 && (
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
                {formatMoney(Math.max(0, liability.original_principal - liability.current_balance))}{' '}
                of {formatMoney(liability.original_principal)} paid down
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
                      (1 - liability.current_balance / liability.original_principal) * 100
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
              <button
                className="liability-page__hint-dismiss"
                onClick={() => setShowLinkPicker(false)}
              >
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

      {/* What this debt is secured against. With a link, equity in one line
          and a way through to the asset; without one, the affordance that
          creates it — the value lives on the asset, stated and dated, never
          typed straight into a liability field. */}
      {securedAsset ? (
        <div className="liability-page__hint liability-page__hint--linked">
          <span>
            Secured by{' '}
            <Link to={`/assets/${securedAsset.id}`} className="liability-page__link">
              {securedAsset.name}
            </Link>
            {securedAsset.current_value !== null && (
              <>
                {' '}
                — worth {formatMoney(securedAsset.current_value)}
                {assetEquity !== null && <>, {formatMoney(assetEquity)} equity across its debts</>}
              </>
            )}
          </span>
          <button
            className="liability-page__hint-dismiss"
            onClick={() => linkAsset.mutate({ liabilityId: liability!.id, assetId: null })}
          >
            Unlink
          </button>
        </div>
      ) : (
        <div className="liability-page__hint">
          {showAssetPicker ? (
            <div className="liability-page__link-picker">
              <span>What is this securing?</span>
              <Combobox
                value={null}
                options={assets.map((a) => ({ id: a.id, label: a.name }))}
                onChange={handleLinkAsset}
                placeholder={assets.length ? 'Choose an asset…' : 'No assets tracked yet'}
                autoFocus
                aria-label="Asset this debt is secured against"
              />
              <Link to="/assets" className="liability-page__link">
                Track a new one
              </Link>
              <button
                className="liability-page__hint-dismiss"
                onClick={() => setShowAssetPicker(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <>
              <span>
                Securing an asset — a home, a vehicle? Link it and this page shows the equity
                between its value and what is owed.
              </span>
              <button className="liability-page__action" onClick={() => setShowAssetPicker(true)}>
                What is this securing?
              </button>
            </>
          )}
        </div>
      )}

      <Surface
        as="section"
        className="liability-page__section"
        header={
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
                  value={effectiveExtra}
                  onChange={(e) => setExtraInput(e.target.value)}
                />
              </label>
              <label className="liability-page__whatif">
                <span>One-off to principal:</span>
                <input
                  type="number"
                  min="0"
                  step="100"
                  inputMode="decimal"
                  placeholder="0"
                  value={curtailInput}
                  onChange={(e) => setCurtailInput(e.target.value)}
                />
              </label>
            </div>
          </div>
        }
      >
        <div className="liability-page__section-body">
          {whatIfSavings && (
            <div className="liability-page__whatif-result">
              {[
                extraPayment > 0 ? `+${formatMoney(extraPayment)}/mo` : null,
                curtailment > 0 ? `${formatMoney(curtailment)} once` : null,
              ]
                .filter(Boolean)
                .join(' and ')}{' '}
              →{' '}
              {whatIfSavings.monthsSooner !== null
                ? `paid off ${whatIfSavings.monthsSooner} month${whatIfSavings.monthsSooner === 1 ? '' : 's'} sooner`
                : 'actually pays off'}
              {' · '}
              {formatMoney(whatIfSavings.interestSaved)} interest saved
              {/* Curtailment IS principal — interest accrues on the balance,
                  so a lump sum can only shrink what next month's interest is
                  computed on. Said here because the question keeps coming. */}
              {curtailment > 0 && <span> — every cent of the one-off is principal</span>}
              {extraPayment > 0 && extraPayment !== storedPlan && (
                <button
                  type="button"
                  className="liability-page__plan-btn"
                  onClick={handleSavePlan}
                  disabled={updateLiability.isPending}
                >
                  Save as my plan
                </button>
              )}
              {storedPlan !== null && extraPayment === storedPlan && (
                <span className="liability-page__plan-note">
                  Your plan
                  <button
                    type="button"
                    className="liability-page__plan-btn"
                    onClick={handleClearPlan}
                    disabled={updateLiability.isPending}
                  >
                    Clear
                  </button>
                </span>
              )}
            </div>
          )}
          {amortization ? (
            liability.current_balance === 0 ? (
              <div className="liability-page__empty">Nothing left to pay down.</div>
            ) : !amortization.terms_complete ? (
              // The curve past today IS the projection. Without terms there is
              // nothing to draw but the balance you already know, so say what is
              // missing rather than render an almost-empty chart.
              <div className="liability-page__empty">
                <p>
                  A paydown curve needs the APR and minimum payment — they decide how much of each
                  payment is interest, and therefore when this is gone.
                </p>
                <button
                  type="button"
                  className="liability-page__empty-action"
                  onClick={() => openModal('liability', liability.id)}
                >
                  <Settings size={13} />
                  Add the terms
                </button>
              </div>
            ) : (
              <PaydownChart amortization={amortization} mode={chartMode} isMobile={isMobile} />
            )
          ) : (
            <div className="liability-page__empty">Loading chart…</div>
          )}
        </div>
      </Surface>

      <Surface
        as="section"
        className="liability-page__section"
        header={
          <div className="liability-page__section-header">
            <h2>Amortization schedule</h2>
            <span className="liability-page__section-sub">At the minimum payment</span>
          </div>
        }
      >
        <div className="liability-page__section-body">
          {amortization ? (
            !amortization.terms_complete ? (
              <div className="liability-page__empty">
                <p>Add this liability&apos;s APR and minimum payment to see its schedule.</p>
                <button
                  type="button"
                  className="liability-page__empty-action"
                  onClick={() => openModal('liability', liability.id)}
                >
                  <Settings size={13} />
                  Add the terms
                </button>
              </div>
            ) : amortization.baseline_never_pays_off &&
              amortization.baseline_schedule.length === 0 ? (
              <div className="liability-page__empty">
                The minimum payment doesn't cover interest — there is no schedule to show.
              </div>
            ) : (
              <Surface variant="sunken" className="liability-page__well">
                <AmortizationTable schedule={amortization.baseline_schedule} />
              </Surface>
            )
          ) : (
            <div className="liability-page__empty">Loading schedule…</div>
          )}
        </div>
      </Surface>

      {showBalanceForm && (
        <DatedAmountForm
          title="Update balance"
          amountLabel="Balance owed"
          placeholder={String(liability.current_balance)}
          pending={createSnapshot.isPending}
          onSubmit={handleSaveBalance}
          onClose={() => setShowBalanceForm(false)}
        />
      )}

      {activeModal?.kind === 'liability' && activeModal.editingId === liability.id && (
        <LiabilitySettingsModal
          budgetId={budgetId}
          liability={liability}
          onClose={closeModal}
          onDeleted={() => navigate('/liabilities')}
        />
      )}
    </div>
  )
}
