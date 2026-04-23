import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { useAccounts, useUpdateAccount } from '../../api/accounts'
import {
  useLinkSimpleFINAccount,
  useUnlinkSimpleFINAccount,
  useUpdateAccountSimpleFINSettings,
  useSimpleFINConnections,
  useSimpleFINRemoteAccounts,
} from '../../api/simplefin'
import { formatSyncAge } from '../simplefin/SyncStatusIcon'
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
  accountId: string
  onClose: () => void
}

export function AccountSettingsModal({ accountId, onClose }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: accounts } = useAccounts(budgetId)
  const account = accounts?.find((a) => a.id === accountId)

  const updateAccount = useUpdateAccount(budgetId ?? '')
  const { data: sfConnections } = useSimpleFINConnections()
  const firstConnection = sfConnections?.[0] ?? null

  const [showLinkPicker, setShowLinkPicker] = useState(false)
  const { data: remoteAccounts = [] } = useSimpleFINRemoteAccounts(
    showLinkPicker ? (firstConnection?.id ?? null) : null,
  )
  const link = useLinkSimpleFINAccount(accountId)
  const unlink = useUnlinkSimpleFINAccount(accountId)
  const updateSyncSettings = useUpdateAccountSimpleFINSettings(accountId)
  const [linkError, setLinkError] = useState<string | null>(null)

  const [name, setName] = useState(account?.name ?? '')
  const [accountType, setAccountType] = useState<AccountType>(
    (account?.account_type as AccountType) ?? 'checking',
  )
  const [onBudget, setOnBudget] = useState(account?.on_budget ?? true)
  const [note, setNote] = useState(account?.note ?? '')
  const [saveError, setSaveError] = useState<string | null>(null)

  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (account) {
      setName(account.name)
      setAccountType(account.account_type as AccountType)
      setOnBudget(account.on_budget)
      setNote(account.note ?? '')
    }
  }, [account])

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

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaveError(null)
    try {
      await updateAccount.mutateAsync({
        id: accountId,
        name: name.trim(),
        account_type: accountType,
        on_budget: accountType === 'tracking' ? false : onBudget,
        note: note.trim() || null,
      })
      onClose()
    } catch {
      setSaveError('Failed to save — please try again')
    }
  }

  async function handleLink(remoteId: string) {
    const selected = remoteAccounts.find((ra) => ra.id === remoteId)
    setLinkError(null)
    try {
      await link.mutateAsync({ id: remoteId, name: selected?.name ?? null })
      setShowLinkPicker(false)
    } catch {
      setLinkError('Failed to link — please try again')
    }
  }

  async function handleUnlink() {
    if (!confirm('Unlink this account from SimpleFIN? Synced transactions will remain.')) return
    await unlink.mutate()
  }

  if (!account) return null

  const isLinked = !!account.simplefin_account_id

  return (
    <div className="acct-modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="acct-modal" role="dialog" aria-modal="true">
        <div className="acct-modal__header">
          <span className="acct-modal__title">Account Settings</span>
          <button className="acct-modal__close" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSave}>
          <div className="acct-modal__body">
            {/* Basic fields */}
            <div className="acct-modal__section">
              <div className="acct-modal__field">
                <label className="acct-modal__label">Name</label>
                <input
                  ref={nameRef}
                  className="acct-modal__input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
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

            {/* SimpleFIN section */}
            {firstConnection && (
              <div className="acct-modal__section acct-modal__section--simplefin">
                <div className="acct-modal__section-title">SimpleFIN Sync</div>
                {isLinked ? (
                  <div className="acct-modal__sf-linked">
                    <div className="acct-modal__sf-name">
                      <span className="acct-modal__sf-badge">Linked</span>
                      {account.simplefin_account_name ?? account.simplefin_account_id}
                    </div>
                    <div className="acct-modal__sf-meta">
                      {formatSyncAge(account.last_simplefin_sync_at ?? null)}
                    </div>
                    <label className="acct-modal__sf-toggle">
                      <input
                        type="checkbox"
                        checked={account.simplefin_sync_enabled ?? true}
                        onChange={(e) => updateSyncSettings.mutate(e.target.checked)}
                      />
                      Sync enabled
                    </label>
                    <button
                      type="button"
                      className="acct-modal__sf-disconnect"
                      onClick={handleUnlink}
                      disabled={unlink.isPending}
                    >
                      Disconnect
                    </button>
                  </div>
                ) : (
                  <div className="acct-modal__sf-unlinked">
                    <span className="acct-modal__sf-none">Not linked to SimpleFIN</span>
                    {!showLinkPicker ? (
                      <button
                        type="button"
                        className="acct-modal__sf-link-btn"
                        onClick={() => setShowLinkPicker(true)}
                      >
                        Link account…
                      </button>
                    ) : (
                      <div className="acct-modal__sf-picker">
                        <select
                          className="acct-modal__input"
                          defaultValue=""
                          disabled={link.isPending}
                          onChange={(e) => e.target.value && handleLink(e.target.value)}
                        >
                          <option value="">
                            {link.isPending ? 'Linking…' : 'Select account…'}
                          </option>
                          {remoteAccounts.map((ra) => (
                            <option key={ra.id} value={ra.id}>
                              {ra.name ?? ra.id}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="acct-modal__sf-cancel"
                          onClick={() => {
                            setShowLinkPicker(false)
                            setLinkError(null)
                          }}
                        >
                          Cancel
                        </button>
                        {linkError && <span className="acct-modal__sf-error">{linkError}</span>}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="acct-modal__footer">
            {saveError && <span className="acct-modal__save-error">{saveError}</span>}
            <button type="button" className="acct-modal__btn acct-modal__btn--cancel" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="acct-modal__btn acct-modal__btn--save"
              disabled={updateAccount.isPending || !name.trim()}
            >
              {updateAccount.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
