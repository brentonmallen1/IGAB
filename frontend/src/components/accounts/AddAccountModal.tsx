import { useEffect, useRef, useState } from 'react'
import { useCreateAccount } from '../../api/accounts'
import { apiErrorMessage } from '../../api/client'
import { useAccountTypes } from '../../api/accountTypes'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { AccountTypeInfoModal } from './AccountTypeInfoModal'
import { AccountTypeField } from './AccountTypeField'
import { CountsAsSavingsField } from './CountsAsSavingsField'
import { useAppStore } from '../../stores/appStore'
import { Dialog } from '../common/Dialog/Dialog'

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
    () =>
      typeOptions.find((t) => t.key === (initialTypeKey ?? 'checking'))?.default_on_budget ?? true
  )
  const [countsAsSavings, setCountsAsSavings] = useState(
    () =>
      typeOptions.find((t) => t.key === (initialTypeKey ?? 'checking'))
        ?.default_counts_as_savings ?? true
  )
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showTypeInfo, setShowTypeInfo] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    nameRef.current?.focus()
  }, [])

  function handleTypeChange(key: string) {
    setAccountType(key)
    // Picking a type resets the checkbox to that type's default; the user can
    // still override it before saving.
    const picked = typeOptions.find((t) => t.key === key)
    if (picked) {
      setOnBudget(picked.default_on_budget)
      setCountsAsSavings(picked.default_counts_as_savings)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!budgetId) return
    if (!name.trim()) {
      setError('Give the account a name')
      return
    }
    setError(null)
    try {
      await createAccount.mutateAsync({
        name: name.trim(),
        account_type: accountType,
        on_budget: onBudget,
        counts_as_savings: countsAsSavings,
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
    <>
      <Dialog
        title="New Account"
        onClose={onClose}
        historyKey="add-account"
        footer={
          <div className="dialog-actions">
            {error && <span className="dialog-form__error">{error}</span>}
            <div className="dialog-actions__end">
              <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                form="add-account-form"
                className="dialog-btn dialog-btn--primary"
                disabled={createAccount.isPending}
              >
                {createAccount.isPending ? 'Creating…' : 'Create Account'}
              </button>
            </div>
          </div>
        }
      >
        <form id="add-account-form" className="dialog-form" onSubmit={handleSubmit}>
          <label className="dialog-form__field">
            <span>Name</span>
            <input
              ref={nameRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Chase Checking"
            />
          </label>
          <AccountTypeField
            value={accountType}
            options={typeOptions}
            onChange={handleTypeChange}
            onHelp={() => setShowTypeInfo(true)}
          />
          <label className="dialog-form__field dialog-form__field--inline">
            <input
              type="checkbox"
              checked={onBudget}
              onChange={(e) => setOnBudget(e.target.checked)}
            />
            <span>On budget</span>
          </label>
          <CountsAsSavingsField
            onBudget={onBudget}
            classification={typeOptions.find((t) => t.key === accountType)?.classification}
            checked={countsAsSavings}
            onChange={setCountsAsSavings}
          />
          <label className="dialog-form__field">
            <span>Note</span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Optional note…"
            />
          </label>
        </form>
      </Dialog>
      {showTypeInfo && (
        <AccountTypeInfoModal
          types={typeRows}
          budgetId={budgetId}
          onClose={() => setShowTypeInfo(false)}
        />
      )}
    </>
  )
}
