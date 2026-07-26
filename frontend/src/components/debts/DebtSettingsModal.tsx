import { useState } from 'react'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../api/accounts'
import {
  useCreateDebt,
  useDebts,
  useDeleteDebt,
  useUpdateDebt,
  type Debt,
  type DebtType,
} from '../../api/debts'
import './DebtSettingsModal.css'

const DEBT_TYPES: { value: DebtType; label: string }[] = [
  { value: 'mortgage', label: 'Mortgage' },
  { value: 'auto', label: 'Auto loan' },
  { value: 'student', label: 'Student loan' },
  { value: 'personal', label: 'Personal loan' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'medical', label: 'Medical' },
  { value: 'other', label: 'Other' },
]

interface Props {
  budgetId: string
  debt: Debt | null // null = create
  onClose: () => void
  onDeleted?: () => void
}

/**
 * Create/edit a debt. The mode switch makes the managed-vs-unmanaged
 * exclusivity obvious: a debt tracks EITHER a real account's ledger OR a
 * manually entered balance — never both.
 */
export function DebtSettingsModal({ budgetId, debt, onClose, onDeleted }: Props) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: debts = [] } = useDebts(budgetId)
  const createDebt = useCreateDebt(budgetId)
  const updateDebt = useUpdateDebt(budgetId)
  const deleteDebt = useDeleteDebt(budgetId)

  const [name, setName] = useState(debt?.name ?? '')
  const [debtType, setDebtType] = useState<DebtType>(debt?.debt_type ?? 'personal')
  const [mode, setMode] = useState<'managed' | 'unmanaged'>(debt?.mode ?? 'unmanaged')
  const [accountId, setAccountId] = useState(debt?.linked_account_id ?? '')
  const [balance, setBalance] = useState(
    debt && debt.mode === 'unmanaged' ? String(debt.current_balance) : ''
  )
  const [rate, setRate] = useState(debt ? String(debt.interest_rate) : '')
  const [minimumPayment, setMinimumPayment] = useState(debt ? String(debt.minimum_payment) : '')
  const [originationDate, setOriginationDate] = useState(debt?.origination_date ?? '')
  const [originalPrincipal, setOriginalPrincipal] = useState(
    debt?.original_principal != null ? String(debt.original_principal) : ''
  )
  const [error, setError] = useState<string | null>(null)

  // Accounts already backing another debt can't back this one too
  const linkedElsewhere = new Set(
    debts.filter((d) => d.id !== debt?.id && d.linked_account_id).map((d) => d.linked_account_id)
  )
  const linkableAccounts = accounts.filter((a) => !linkedElsewhere.has(a.id))

  const isPending = createDebt.isPending || updateDebt.isPending || deleteDebt.isPending

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return setError('Give this debt a name')
    const rateNum = parseFloat(rate)
    if (isNaN(rateNum) || rateNum < 0) return setError('Enter a non-negative interest rate')
    const paymentNum = parseFloat(minimumPayment)
    if (isNaN(paymentNum) || paymentNum < 0) return setError('Enter the minimum monthly payment')
    if (mode === 'managed' && !accountId) return setError('Choose the account this debt lives in')
    const balanceNum = parseFloat(balance)
    if (mode === 'unmanaged' && (isNaN(balanceNum) || balanceNum < 0)) {
      return setError('Enter the current balance owed')
    }
    setError(null)

    const shared = {
      name: name.trim(),
      debt_type: debtType,
      interest_rate: rateNum,
      minimum_payment: paymentNum,
      origination_date: originationDate || null,
      original_principal: originalPrincipal ? parseFloat(originalPrincipal) : null,
    }

    try {
      if (debt) {
        await updateDebt.mutateAsync({
          debtId: debt.id,
          ...shared,
          ...(mode === 'managed'
            ? { linked_account_id: accountId }
            : { linked_account_id: null, manual_balance: balanceNum }),
        })
      } else {
        await createDebt.mutateAsync({
          ...shared,
          ...(mode === 'managed'
            ? { linked_account_id: accountId }
            : { manual_balance: balanceNum }),
        })
      }
      toast.success(debt ? 'Debt updated' : `Now tracking ${name.trim()}`)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail
      setError(typeof detail === 'string' ? detail : 'Save failed')
    }
  }

  async function handleDelete() {
    if (!debt) return
    if (!confirm(`Stop tracking "${debt.name}"? This won't touch any accounts or transactions.`))
      return
    await deleteDebt.mutateAsync(debt.id)
    toast.success('Debt removed')
    onClose()
    onDeleted?.()
  }

  return (
    <div
      className="debt-modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="debt-modal" role="dialog" aria-modal aria-labelledby="debt-modal-title">
        <div className="debt-modal__header">
          <span id="debt-modal-title" className="debt-modal__title">
            {debt ? 'Debt settings' : 'Track a debt'}
          </span>
          <button className="debt-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <form className="debt-modal__body" onSubmit={handleSubmit}>
          <label className="debt-modal__field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus placeholder="Car loan" />
          </label>

          <div className="debt-modal__row">
            <label className="debt-modal__field">
              <span>Type</span>
              <select value={debtType} onChange={(e) => setDebtType(e.target.value as DebtType)}>
                {DEBT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="debt-modal__field">
              <span>Interest rate (% / yr)</span>
              <input
                type="number"
                min="0"
                step="0.001"
                inputMode="decimal"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                placeholder="6.25"
              />
            </label>
            <label className="debt-modal__field">
              <span>Minimum payment</span>
              <input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={minimumPayment}
                onChange={(e) => setMinimumPayment(e.target.value)}
                placeholder="275.00"
              />
            </label>
          </div>

          <fieldset className="debt-modal__mode">
            <legend>Where does the balance come from?</legend>
            <label className={`debt-modal__mode-option ${mode === 'managed' ? 'debt-modal__mode-option--active' : ''}`}>
              <input
                type="radio"
                name="debt-mode"
                checked={mode === 'managed'}
                onChange={() => setMode('managed')}
              />
              <span>
                <strong>An account in this budget</strong>
                <small>Balance and payments track the account's ledger automatically</small>
              </span>
            </label>
            <label className={`debt-modal__mode-option ${mode === 'unmanaged' ? 'debt-modal__mode-option--active' : ''}`}>
              <input
                type="radio"
                name="debt-mode"
                checked={mode === 'unmanaged'}
                onChange={() => setMode('unmanaged')}
              />
              <span>
                <strong>I'll enter it myself</strong>
                <small>For debts without an account here — update the balance as you pay</small>
              </span>
            </label>

            {mode === 'managed' ? (
              <label className="debt-modal__field debt-modal__mode-detail">
                <span>Account</span>
                <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  <option value="" disabled>
                    Choose an account…
                  </option>
                  {linkableAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="debt-modal__field debt-modal__mode-detail">
                <span>Current balance owed</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  value={balance}
                  onChange={(e) => setBalance(e.target.value)}
                  placeholder="9480.00"
                />
              </label>
            )}
          </fieldset>

          <details className="debt-modal__optional">
            <summary>Optional details</summary>
            <div className="debt-modal__row">
              <label className="debt-modal__field">
                <span>Origination date</span>
                <input
                  type="date"
                  value={originationDate}
                  onChange={(e) => setOriginationDate(e.target.value)}
                />
              </label>
              <label className="debt-modal__field">
                <span>Original principal</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  value={originalPrincipal}
                  onChange={(e) => setOriginalPrincipal(e.target.value)}
                />
              </label>
            </div>
          </details>

          {error && <div className="debt-modal__error">{error}</div>}

          <div className="debt-modal__footer">
            {debt ? (
              <button
                type="button"
                className="debt-modal__btn debt-modal__btn--danger"
                onClick={handleDelete}
                disabled={isPending}
              >
                Delete
              </button>
            ) : (
              <span />
            )}
            <div className="debt-modal__actions">
              <button
                type="button"
                className="debt-modal__btn debt-modal__btn--secondary"
                onClick={onClose}
                disabled={isPending}
              >
                Cancel
              </button>
              <button type="submit" className="debt-modal__btn debt-modal__btn--primary" disabled={isPending}>
                {isPending ? 'Saving…' : debt ? 'Save' : 'Start tracking'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
