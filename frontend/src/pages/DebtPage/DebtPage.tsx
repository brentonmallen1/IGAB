import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Settings } from 'lucide-react'
import toast from 'react-hot-toast'
import { useCategories, useCategoryGroups } from '../../api/categories'
import {
  useCreateDebtSnapshot,
  useDebtAmortization,
  useDebts,
  useLinkCategoryDebt,
} from '../../api/debts'
import { AmortizationTable } from '../../components/debts/AmortizationTable'
import { DebtSettingsModal } from '../../components/debts/DebtSettingsModal'
import { PaydownChart } from '../../components/debts/PaydownChart'
import { PayoffPill } from '../../components/debts/PayoffPill'
import { Combobox } from '../../components/common/Combobox/Combobox'
import { MetricCard } from '../../components/reports/MetricCard'
import { useIsMobile } from '../../hooks/useMediaQuery'
import { useAppStore } from '../../stores/appStore'
import { useUIStore } from '../../stores/uiStore'
import { formatMoney } from '../../utils/money'
import './DebtPage.css'

const TYPE_LABELS: Record<string, string> = {
  mortgage: 'Mortgage',
  auto: 'Auto loan',
  student: 'Student loan',
  personal: 'Personal loan',
  credit_card: 'Credit card',
  medical: 'Medical',
  other: 'Other',
}

export function DebtPage() {
  const { debtId } = useParams<{ debtId: string }>()
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const navigate = useNavigate()
  const isMobile = useIsMobile()

  const { data: debts = [], isLoading } = useDebts(budgetId)
  const debt = debts.find((d) => d.id === debtId) ?? null

  const { isDebtEditorOpen, editingDebtId, openDebtEditor, closeDebtEditor } = useUIStore()

  const [chartMode, setChartMode] = useState<'now' | 'beginning'>('now')
  const [extraInput, setExtraInput] = useState('')
  const [extraPayment, setExtraPayment] = useState(0)
  const [showBalanceForm, setShowBalanceForm] = useState(false)
  const [newBalance, setNewBalance] = useState('')
  const [balanceDate, setBalanceDate] = useState('')
  const [showLinkPicker, setShowLinkPicker] = useState(false)

  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const createSnapshot = useCreateDebtSnapshot(budgetId)
  const linkCategory = useLinkCategoryDebt(budgetId)

  // Debounce the what-if input so typing doesn't spam the API
  useEffect(() => {
    const handle = setTimeout(() => {
      const parsed = parseFloat(extraInput)
      setExtraPayment(!isNaN(parsed) && parsed > 0 ? parsed : 0)
    }, 400)
    return () => clearTimeout(handle)
  }, [extraInput])

  const { data: amortization } = useDebtAmortization(budgetId, debtId ?? null, {
    extraPayment,
    fromOrigination: chartMode === 'beginning',
  })

  if (!budgetId || !debtId) return null
  if (isLoading) {
    return <div className="debt-page"><div className="debt-page__empty">Loading…</div></div>
  }
  if (!debt) {
    return (
      <div className="debt-page">
        <div className="debt-page__empty">
          This debt doesn't exist anymore. <Link to="/debts">Back to debts</Link>
        </div>
      </div>
    )
  }

  const linkedCategory = categories.find((c) => c.id === debt.linked_category_id) ?? null
  const systemGroupIds = new Set(groups.filter((g) => g.is_system).map((g) => g.id))
  const linkableCategories = categories.filter(
    (c) =>
      !c.is_hidden &&
      !systemGroupIds.has(c.category_group_id) &&
      !c.linked_account_id
  )

  const monthsRemaining = amortization?.baseline_never_pays_off
    ? null
    : amortization?.baseline_schedule.length ?? null

  async function handleSaveBalance(e: React.FormEvent) {
    e.preventDefault()
    const parsed = parseFloat(newBalance)
    if (isNaN(parsed) || parsed < 0) return
    await createSnapshot.mutateAsync({
      debtId: debt!.id,
      balance: parsed,
      ...(balanceDate ? { date: balanceDate } : {}),
    })
    toast.success('Balance updated')
    setShowBalanceForm(false)
    setNewBalance('')
    setBalanceDate('')
  }

  async function handleLinkCategory(categoryId: string | null) {
    if (!categoryId) return
    await linkCategory.mutateAsync({ categoryId, debtId: debt!.id })
    const name = categories.find((c) => c.id === categoryId)?.name
    toast.success(`Payments now tracked from ${name ?? 'category'}`)
    setShowLinkPicker(false)
  }

  async function handleUnlinkCategory() {
    if (!linkedCategory) return
    await linkCategory.mutateAsync({ categoryId: linkedCategory.id, debtId: null })
    toast.success('Category unlinked')
  }

  const whatIfSavings =
    amortization?.extra_schedule && !amortization.extra_never_pays_off && extraPayment > 0
      ? {
          monthsSooner: amortization.baseline_never_pays_off
            ? null
            : amortization.baseline_schedule.length - amortization.extra_schedule.length,
          interestSaved: amortization.baseline_total_interest - (amortization.extra_total_interest ?? 0),
        }
      : null

  return (
    <div className="debt-page">
      <div className="debt-page__header">
        <div className="debt-page__header-left">
          <h1 className="debt-page__name">{debt.name}</h1>
          <span className="debt-page__badge">{TYPE_LABELS[debt.debt_type] ?? 'Other'}</span>
          <span className="debt-page__badge debt-page__badge--muted">
            {debt.mode === 'managed' ? 'Managed' : 'Unmanaged'}
          </span>
          <button
            className="debt-page__settings"
            onClick={() => openDebtEditor(debt.id)}
            aria-label="Debt settings"
            title="Debt settings"
          >
            <Settings size={14} />
          </button>
        </div>
        <div className="debt-page__header-actions">
          {debt.mode === 'managed' && debt.linked_account_id && (
            <Link className="debt-page__link" to={`/accounts/${debt.linked_account_id}`}>
              View account register
            </Link>
          )}
          {debt.mode === 'unmanaged' && (
            <button className="debt-page__action" onClick={() => setShowBalanceForm(true)}>
              Update balance
            </button>
          )}
        </div>
      </div>

      <div className="debt-page__pill-row">
        <PayoffPill debt={debt} />
      </div>

      <div className="debt-page__metrics">
        <MetricCard
          label="Current Balance"
          value={formatMoney(Number(debt.current_balance))}
          accent
        />
        <MetricCard label="Interest Rate" value={`${Number(debt.interest_rate)}%`} />
        <MetricCard
          label="Interest Remaining"
          value={
            amortization
              ? amortization.baseline_never_pays_off
                ? '—'
                : formatMoney(Number(amortization.baseline_total_interest))
              : '…'
          }
          sub={amortization?.baseline_never_pays_off ? 'Never pays off at minimum' : 'At minimum payment'}
        />
        <MetricCard
          label="Months Remaining"
          value={monthsRemaining === null ? '—' : String(monthsRemaining)}
          sub="At minimum payment"
        />
      </div>

      {debt.mode === 'unmanaged' && !linkedCategory && (
        <div className="debt-page__hint">
          {showLinkPicker ? (
            <div className="debt-page__link-picker">
              <span>Track payments from:</span>
              <Combobox
                value={null}
                options={linkableCategories.map((c) => ({ id: c.id, label: c.name }))}
                onChange={handleLinkCategory}
                placeholder="Choose a category…"
                autoFocus
                aria-label="Category to track payments from"
              />
              <button className="debt-page__hint-dismiss" onClick={() => setShowLinkPicker(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <>
              <span>
                Link a budget category to track real payments — its spending becomes this
                debt's payment history.
              </span>
              <button className="debt-page__action" onClick={() => setShowLinkPicker(true)}>
                Link a category
              </button>
            </>
          )}
        </div>
      )}
      {linkedCategory && (
        <div className="debt-page__hint debt-page__hint--linked">
          <span>
            Payments tracked from <strong>{linkedCategory.name}</strong>
          </span>
          <button className="debt-page__hint-dismiss" onClick={handleUnlinkCategory}>
            Unlink
          </button>
        </div>
      )}

      <div className="debt-page__section">
        <div className="debt-page__section-header">
          <h2>Paydown</h2>
          <div className="debt-page__chart-controls">
            <div className="debt-page__toggle">
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
            <label className="debt-page__whatif">
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
          <div className="debt-page__whatif-result">
            +{formatMoney(extraPayment)}/mo →{' '}
            {whatIfSavings.monthsSooner !== null
              ? `paid off ${whatIfSavings.monthsSooner} month${whatIfSavings.monthsSooner === 1 ? '' : 's'} sooner`
              : 'actually pays off'}
            {' · '}
            {formatMoney(Number(whatIfSavings.interestSaved))} interest saved
          </div>
        )}
        {amortization ? (
          Number(debt.current_balance) === 0 ? (
            <div className="debt-page__empty">Nothing left to pay down.</div>
          ) : (
            <PaydownChart amortization={amortization} mode={chartMode} isMobile={isMobile} />
          )
        ) : (
          <div className="debt-page__empty">Loading chart…</div>
        )}
      </div>

      <div className="debt-page__section">
        <div className="debt-page__section-header">
          <h2>Amortization schedule</h2>
          <span className="debt-page__section-sub">At the minimum payment</span>
        </div>
        {amortization ? (
          amortization.baseline_never_pays_off && amortization.baseline_schedule.length === 0 ? (
            <div className="debt-page__empty">
              The minimum payment doesn't cover interest — there is no schedule to show.
            </div>
          ) : (
            <AmortizationTable schedule={amortization.baseline_schedule} />
          )
        ) : (
          <div className="debt-page__empty">Loading schedule…</div>
        )}
      </div>

      {showBalanceForm && (
        <div
          className="debt-page__balance-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowBalanceForm(false)
          }}
        >
          <form className="debt-page__balance-form" onSubmit={handleSaveBalance}>
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
                placeholder={String(debt.current_balance)}
              />
            </label>
            <label>
              <span>As of (optional — defaults to today)</span>
              <input type="date" value={balanceDate} onChange={(e) => setBalanceDate(e.target.value)} />
            </label>
            <div className="debt-page__balance-actions">
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

      {isDebtEditorOpen && editingDebtId === debt.id && (
        <DebtSettingsModal
          budgetId={budgetId}
          debt={debt}
          onClose={closeDebtEditor}
          onDeleted={() => navigate('/debts')}
        />
      )}
    </div>
  )
}
