import { useState } from 'react'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../api/accounts'
import {
  useCreateLiability,
  useLiabilities,
  useDeleteLiability,
  useUpdateLiability,
  type Liability,
  type LiabilityType,
} from '../../api/liabilities'
import './LiabilitySettingsModal.css'

const LIABILITY_TYPES: { value: LiabilityType; label: string }[] = [
  { value: 'mortgage', label: 'Mortgage' },
  { value: 'auto', label: 'Auto loan' },
  { value: 'student', label: 'Student loan' },
  { value: 'personal', label: 'Personal loan' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'medical', label: 'Medical' },
  { value: 'other', label: 'Other' },
]

export interface LiabilityPrefill {
  accountId: string
  accountName: string
  liabilityType?: LiabilityType
}

interface Props {
  budgetId: string
  liability: Liability | null // null = create
  onClose: () => void
  onDeleted?: () => void
  prefill?: LiabilityPrefill // for suggesting from an untracked account
}

/**
 * Create/edit a liability. The mode switch makes the managed-vs-unmanaged
 * exclusivity obvious: a liability tracks EITHER a real account's ledger OR a
 * manually entered balance — never both.
 */
export function LiabilitySettingsModal({ budgetId, liability, onClose, onDeleted, prefill }: Props) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const createLiability = useCreateLiability(budgetId)
  const updateLiability = useUpdateLiability(budgetId)
  const deleteLiability = useDeleteLiability(budgetId)

  const [name, setName] = useState(liability?.name ?? prefill?.accountName ?? '')
  const [liabilityType, setLiabilityType] = useState<LiabilityType>(
    liability?.liability_type ?? prefill?.liabilityType ?? 'personal'
  )
  const [mode, setMode] = useState<'managed' | 'unmanaged'>(
    liability?.mode ?? (prefill ? 'managed' : 'unmanaged')
  )
  const [accountId, setAccountId] = useState(liability?.linked_account_id ?? prefill?.accountId ?? '')
  const [balance, setBalance] = useState(
    liability && liability.mode === 'unmanaged' ? String(liability.current_balance) : ''
  )
  const [rate, setRate] = useState(liability ? String(liability.interest_rate) : '')
  const [minimumPayment, setMinimumPayment] = useState(
    liability ? String(liability.minimum_payment) : ''
  )
  const [originationDate, setOriginationDate] = useState(liability?.origination_date ?? '')
  const [originalPrincipal, setOriginalPrincipal] = useState(
    liability?.original_principal != null ? String(liability.original_principal) : ''
  )
  const [error, setError] = useState<string | null>(null)

  // Accounts already backing another liability can't back this one too
  const linkedElsewhere = new Set(
    liabilities
      .filter((l) => l.id !== liability?.id && l.linked_account_id)
      .map((l) => l.linked_account_id)
  )
  const linkableAccounts = accounts.filter((a) => !linkedElsewhere.has(a.id))

  const isPending =
    createLiability.isPending || updateLiability.isPending || deleteLiability.isPending

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return setError('Give this liability a name')
    const rateNum = parseFloat(rate)
    if (isNaN(rateNum) || rateNum < 0) return setError('Enter a non-negative interest rate')
    const paymentNum = parseFloat(minimumPayment)
    if (isNaN(paymentNum) || paymentNum < 0) return setError('Enter the minimum monthly payment')
    if (mode === 'managed' && !accountId)
      return setError('Choose the account this liability lives in')
    const balanceNum = parseFloat(balance)
    if (mode === 'unmanaged' && (isNaN(balanceNum) || balanceNum < 0)) {
      return setError('Enter the current balance owed')
    }
    setError(null)

    const shared = {
      name: name.trim(),
      liability_type: liabilityType,
      interest_rate: rateNum,
      minimum_payment: paymentNum,
      origination_date: originationDate || null,
      original_principal: originalPrincipal ? parseFloat(originalPrincipal) : null,
    }

    try {
      if (liability) {
        await updateLiability.mutateAsync({
          liabilityId: liability.id,
          ...shared,
          ...(mode === 'managed'
            ? { linked_account_id: accountId }
            : { linked_account_id: null, manual_balance: balanceNum }),
        })
      } else {
        await createLiability.mutateAsync({
          ...shared,
          ...(mode === 'managed'
            ? { linked_account_id: accountId }
            : { manual_balance: balanceNum }),
        })
      }
      toast.success(liability ? 'Liability updated' : `Now tracking ${name.trim()}`)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Save failed')
    }
  }

  async function handleDelete() {
    if (!liability) return
    if (
      !confirm(
        `Stop tracking "${liability.name}"? This won't touch any accounts or transactions.`
      )
    )
      return
    await deleteLiability.mutateAsync(liability.id)
    toast.success('Liability removed')
    onClose()
    onDeleted?.()
  }

  return (
    <div
      className="liability-modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="liability-modal"
        role="dialog"
        aria-modal
        aria-labelledby="liability-modal-title"
      >
        <div className="liability-modal__header">
          <span id="liability-modal-title" className="liability-modal__title">
            {liability ? 'Liability settings' : 'Track a liability'}
          </span>
          <button className="liability-modal__close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <form className="liability-modal__body" onSubmit={handleSubmit}>
          <label className="liability-modal__field">
            <span>Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              placeholder="Car loan"
            />
          </label>

          <div className="liability-modal__row">
            <label className="liability-modal__field">
              <span>Type</span>
              <select
                value={liabilityType}
                onChange={(e) => setLiabilityType(e.target.value as LiabilityType)}
              >
                {LIABILITY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="liability-modal__field">
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
            <label className="liability-modal__field">
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

          <fieldset className="liability-modal__mode">
            <legend>Where does the balance come from?</legend>
            <label
              className={`liability-modal__mode-option ${mode === 'managed' ? 'liability-modal__mode-option--active' : ''}`}
            >
              <input
                type="radio"
                name="liability-mode"
                checked={mode === 'managed'}
                onChange={() => setMode('managed')}
              />
              <span>
                <strong>An account in this budget</strong>
                <small>Balance and payments track the account's ledger automatically</small>
              </span>
            </label>
            <label
              className={`liability-modal__mode-option ${mode === 'unmanaged' ? 'liability-modal__mode-option--active' : ''}`}
            >
              <input
                type="radio"
                name="liability-mode"
                checked={mode === 'unmanaged'}
                onChange={() => setMode('unmanaged')}
              />
              <span>
                <strong>I'll enter it myself</strong>
                <small>For liabilities without an account here — update the balance as you pay</small>
              </span>
            </label>

            {mode === 'managed' ? (
              <label className="liability-modal__field liability-modal__mode-detail">
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
              <label className="liability-modal__field liability-modal__mode-detail">
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

          <details className="liability-modal__optional">
            <summary>Optional details</summary>
            <div className="liability-modal__row">
              <label className="liability-modal__field">
                <span>Origination date</span>
                <input
                  type="date"
                  value={originationDate}
                  onChange={(e) => setOriginationDate(e.target.value)}
                />
              </label>
              <label className="liability-modal__field">
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

          {error && <div className="liability-modal__error">{error}</div>}

          <div className="liability-modal__footer">
            {liability ? (
              <button
                type="button"
                className="liability-modal__btn liability-modal__btn--danger"
                onClick={handleDelete}
                disabled={isPending}
              >
                Delete
              </button>
            ) : (
              <span />
            )}
            <div className="liability-modal__actions">
              <button
                type="button"
                className="liability-modal__btn liability-modal__btn--secondary"
                onClick={onClose}
                disabled={isPending}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="liability-modal__btn liability-modal__btn--primary"
                disabled={isPending}
              >
                {isPending ? 'Saving…' : liability ? 'Save' : 'Start tracking'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}
