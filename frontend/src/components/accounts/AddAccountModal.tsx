import { useEffect, useRef, useState } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { useCreateAccount } from '../../api/accounts'
import { apiErrorMessage } from '../../api/client'
import { useAccountTypes } from '../../api/accountTypes'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { AccountTypeInfoModal } from './AccountTypeInfoModal'
import { useAppStore } from '../../stores/appStore'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import './AccountSettingsModal.css'

interface Props {
  onClose: () => void
  /** Preselect a type (e.g. the sidebar's Assets + opens with 'investment') */
  initialTypeKey?: string
}

export function AddAccountModal({ onClose, initialTypeKey }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const createAccount = useCreateAccount(budgetId ?? '')
  // Registry-driven: built-ins plus this budget's custom types. The constant
  // fallback only covers the frame before the registry query resolves.
  const { data: typeRows } = useAccountTypes(budgetId)
  const typeOptions = typeRows ?? BUILTIN_ACCOUNT_TYPES
  const [name, setName] = useState('')
  const [accountType, setAccountType] = useState(initialTypeKey ?? 'checking')
  const [onBudget, setOnBudget] = useState(
    () => typeOptions.find((t) => t.key === (initialTypeKey ?? 'checking'))?.default_on_budget ?? true
  )
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showTypeInfo, setShowTypeInfo] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  useEffect(() => {
    nameRef.current?.focus()
  }, [])

  function handleTypeChange(key: string) {
    setAccountType(key)
    // Picking a type resets the checkbox to that type's default; the user can
    // still override it before saving.
    const picked = typeOptions.find((t) => t.key === key)
    if (picked) setOnBudget(picked.default_on_budget)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim() || !budgetId) return
    setError(null)
    try {
      await createAccount.mutateAsync({
        name: name.trim(),
        account_type: accountType,
        on_budget: onBudget,
        note: note.trim() || undefined,
      })
      onClose()
    } catch (err: unknown) {
      // The server names the problem — "An account with that name already
      // exists in this budget" — and "please try again" was the one piece of
      // advice guaranteed not to work for it.
      setError(apiErrorMessage(err, 'Could not create the account'))
    }
  }

  return (
    <div className="acct-modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={trapRef} tabIndex={-1} className="acct-modal" role="dialog" aria-modal="true" aria-labelledby="add-acct-title">
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
                <label className="acct-modal__label">
                  Type
                  <button
                    type="button"
                    className="acct-modal__type-help"
                    onClick={() => setShowTypeInfo(true)}
                    aria-label="What do account types mean?"
                    title="What do account types mean?"
                  >
                    <HelpCircle size={12} />
                  </button>
                </label>
                <select
                  className="acct-modal__input"
                  value={accountType}
                  onChange={(e) => handleTypeChange(e.target.value)}
                >
                  {typeOptions.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="acct-modal__field acct-modal__field--row">
                <label className="acct-modal__label">On Budget</label>
                <input
                  type="checkbox"
                  checked={onBudget}
                  onChange={(e) => setOnBudget(e.target.checked)}
                />
              </div>
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
      {showTypeInfo && (
        <AccountTypeInfoModal types={typeRows} onClose={() => setShowTypeInfo(false)} />
      )}
    </div>
  )
}
