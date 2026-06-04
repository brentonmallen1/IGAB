import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useCreateAccount } from '../../api/accounts'
import { useAppStore } from '../../stores/appStore'
import type { AccountType } from '../../types'
import './AccountSettingsModal.css'

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'credit_card', label: 'Credit Card' },
  { value: 'loan', label: 'Loan' },
  { value: 'tracking', label: 'Tracking' },
]

interface Props {
  onClose: () => void
}

export function AddAccountModal({ onClose }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const createAccount = useCreateAccount(budgetId ?? '')
  const [name, setName] = useState('')
  const [accountType, setAccountType] = useState<AccountType>('checking')
  const [onBudget, setOnBudget] = useState(true)
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    nameRef.current?.focus()
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !budgetId) return
    setError(null)
    try {
      await createAccount.mutateAsync({
        name: name.trim(),
        account_type: accountType,
        on_budget: accountType === 'tracking' ? false : onBudget,
        note: note.trim() || undefined,
      })
      onClose()
    } catch {
      setError('Failed to create account — please try again')
    }
  }

  return (
    <div className="acct-modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="acct-modal" role="dialog" aria-modal="true" aria-labelledby="add-acct-title">
        <div className="acct-modal__header">
          <span id="add-acct-title" className="acct-modal__title">New Account</span>
          <button className="acct-modal__close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="acct-modal__body">
            <div className="acct-modal__section">
              <div className="acct-modal__field">
                <label className="acct-modal__label">Name</label>
                <input
                  ref={nameRef}
                  className="acct-modal__input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  placeholder="e.g. Chase Checking"
                />
              </div>
              <div className="acct-modal__field">
                <label className="acct-modal__label">Type</label>
                <select
                  className="acct-modal__input"
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value as AccountType)}
                >
                  {ACCOUNT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              {accountType !== 'tracking' && (
                <div className="acct-modal__field acct-modal__field--row">
                  <label className="acct-modal__label">On Budget</label>
                  <input
                    type="checkbox"
                    checked={onBudget}
                    onChange={(e) => setOnBudget(e.target.checked)}
                  />
                </div>
              )}
              <div className="acct-modal__field">
                <label className="acct-modal__label">Note</label>
                <input
                  className="acct-modal__input"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Optional note…"
                />
              </div>
            </div>
          </div>

          <div className="acct-modal__footer">
            {error && <span className="acct-modal__save-error">{error}</span>}
            <button type="button" className="acct-modal__btn acct-modal__btn--cancel" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="acct-modal__btn acct-modal__btn--save"
              disabled={createAccount.isPending || !name.trim()}
            >
              {createAccount.isPending ? 'Creating…' : 'Create Account'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
