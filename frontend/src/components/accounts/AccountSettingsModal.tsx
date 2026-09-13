import { useEffect, useRef, useState } from 'react'
import { HelpCircle } from 'lucide-react'
import { useAccounts, useUpdateAccount, useScanDuplicates } from '../../api/accounts'
import {
  useLinkSimpleFINAccount,
  useUnlinkSimpleFINAccount,
  useUpdateAccountSimpleFINSettings,
  useSimpleFINConnections,
  useSimpleFINRemoteAccounts,
} from '../../api/simplefin'
import { formatSyncAge } from '../simplefin/SyncStatusIcon'
import { Dialog } from '../common/Dialog/Dialog'
import { useFormatters } from '../../hooks/useFormatters'
import { useAppStore } from '../../stores/appStore'
import { useAccountTypes } from '../../api/accountTypes'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { AccountTypeInfoModal } from './AccountTypeInfoModal'
import { CountsAsSavingsField } from './CountsAsSavingsField'
import './AccountSettingsModal.css'
import { AccountNumbersSection } from './AccountNumbersSection'
import { confirmAsync } from '../../stores/confirmStore'
import { closeAccountMessage } from './closeAccountMessage'

interface Props {
  accountId: string
  onClose: () => void
}

export function AccountSettingsModal({ accountId, onClose }: Props) {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: accounts } = useAccounts(budgetId, { includeClosed: true })
  const account = accounts?.find((a) => a.id === accountId)
  const { formatMoney } = useFormatters()

  const updateAccount = useUpdateAccount(budgetId ?? '')
  const { data: sfConnections } = useSimpleFINConnections()
  const firstConnection = sfConnections?.[0] ?? null

  const [showLinkPicker, setShowLinkPicker] = useState(false)
  // Fetched from the moment the modal opens, not when the picker does: the
  // list is a live round trip to the SimpleFIN bridge, and a native <select>
  // whose options arrive while it is open closes itself — the picker used to
  // open empty, snap shut, and only show accounts on the second try.
  const { data: remoteAccounts = [], isFetching: remoteLoading } = useSimpleFINRemoteAccounts(
    account?.simplefin_account_id ? null : (firstConnection?.id ?? null)
  )
  const link = useLinkSimpleFINAccount(accountId)
  const unlink = useUnlinkSimpleFINAccount(accountId)
  const updateSyncSettings = useUpdateAccountSimpleFINSettings(accountId)
  const scanDuplicates = useScanDuplicates()
  const [scanResult, setScanResult] = useState<number | null>(null)
  const [linkError, setLinkError] = useState<string | null>(null)

  const { data: typeRows } = useAccountTypes(budgetId)
  const typeOptions = typeRows ?? BUILTIN_ACCOUNT_TYPES

  const [name, setName] = useState(account?.name ?? '')
  const [accountType, setAccountType] = useState(account?.account_type ?? 'checking')
  const [onBudget, setOnBudget] = useState(account?.on_budget ?? true)
  const [countsAsSavings, setCountsAsSavings] = useState(account?.counts_as_savings ?? true)
  const [note, setNote] = useState(account?.note ?? '')
  const [budgetStart, setBudgetStart] = useState(account?.budget_start_date ?? '')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [closeError, setCloseError] = useState<string | null>(null)
  const [showTypeInfo, setShowTypeInfo] = useState(false)

  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (account) {
      setName(account.name)
      setAccountType(account.account_type)
      setOnBudget(account.on_budget)
      setCountsAsSavings(account.counts_as_savings)
      setNote(account.note ?? '')
      setBudgetStart(account.budget_start_date ?? '')
    }
  }, [account])

  useEffect(() => {
    nameRef.current?.focus()
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setSaveError(null)
    try {
      await updateAccount.mutateAsync({
        id: accountId,
        name: name.trim(),
        account_type: accountType,
        on_budget: onBudget,
        counts_as_savings: countsAsSavings,
        note: note.trim() || null,
        // Empty clears it: null means "treat all history as budgeted",
        // which is what an account that was never asked does.
        budget_start_date: budgetStart || null,
      })
      onClose()
    } catch {
      setSaveError('Failed to save — please try again')
    }
  }

  async function handleToggleClosed() {
    if (!account) return
    setCloseError(null)
    const action = account.is_closed ? 'reopen' : 'close'
    // Closing moves no money, and on an account still holding some that is
    // worth saying out loud — quietly hiding it would read as the balance, the
    // debt or the reserve vanishing. The rule lives in closeAccountMessage so
    // it can be read and tested without opening a modal; null means closing is
    // only tidying and there is nothing to warn about.
    const warning = closeAccountMessage(account, formatMoney)
    const ok = await confirmAsync({
      title: `${action === 'close' ? 'Close' : 'Reopen'} this account?`,
      confirmLabel: action === 'close' ? 'Close account' : 'Reopen account',
      ...(action === 'close' && warning ? { message: warning } : {}),
    })
    if (!ok) return
    try {
      await updateAccount.mutateAsync({ id: accountId, is_closed: !account.is_closed })
      onClose()
    } catch {
      setCloseError(`Failed to ${action} account — please try again`)
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
    const ok = await confirmAsync({
      title: 'Unlink this account from SimpleFIN?',
      message: 'Synced transactions will remain.',
      confirmLabel: 'Unlink',
      destructive: true,
    })
    if (!ok) return
    await unlink.mutate()
  }

  if (!account) return null

  const isLinked = !!account.simplefin_account_id

  return (
    <>
      <Dialog
        title="Account Settings"
        onClose={onClose}
        historyKey="account-settings"
        className="acct-modal"
        footer={
          <div className="acct-modal__footer">
            <button
              type="button"
              className={`acct-modal__btn acct-modal__btn--danger`}
              onClick={handleToggleClosed}
              disabled={updateAccount.isPending}
            >
              {account.is_closed ? 'Reopen Account' : 'Close Account'}
            </button>
            {(saveError || closeError) && (
              <span className="acct-modal__save-error">{saveError ?? closeError}</span>
            )}
            <button
              type="button"
              className="acct-modal__btn acct-modal__btn--cancel"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              form="acct-settings-form"
              className="acct-modal__btn acct-modal__btn--save"
              disabled={updateAccount.isPending || !name.trim()}
            >
              {updateAccount.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        }
      >
        <form id="acct-settings-form" onSubmit={handleSave}>
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
                  onChange={(e) => {
                    setAccountType(e.target.value)
                    // A different type brings its own default for the flag,
                    // as on the New Account form. Saving is still the only
                    // thing that changes the account.
                    const picked = typeOptions.find((t) => t.key === e.target.value)
                    if (picked) setCountsAsSavings(picked.default_counts_as_savings)
                  }}
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
              <CountsAsSavingsField
                onBudget={onBudget}
                classification={typeOptions.find((t) => t.key === accountType)?.classification}
                checked={countsAsSavings}
                onChange={setCountsAsSavings}
              />
              <div className="acct-modal__field">
                <label className="acct-modal__label">Note</label>
                <input
                  className="acct-modal__input"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Optional note…"
                />
              </div>
              <AccountNumbersSection
                account={account}
                onSave={(patch) => updateAccount.mutateAsync({ id: accountId, ...patch })}
              />
              {/* The answer to "my card came in with three months of history
                  and now everything is red". That spending predates the
                  budget: it is opening debt, not overspending to cover. */}
              <div className="acct-modal__field">
                <label className="acct-modal__label" htmlFor="acct-budget-start">
                  Budget starts
                </label>
                <input
                  id="acct-budget-start"
                  type="date"
                  className="acct-modal__input"
                  value={budgetStart}
                  onChange={(e) => setBudgetStart(e.target.value)}
                />
                <p className="acct-modal__hint">
                  {budgetStart
                    ? 'Anything before this is opening balance — kept in the register, left ' +
                      'uncategorized, and not counted as needing a category. On a card it shows ' +
                      'as Uncovered and is paid down by assigning to the card.'
                    : 'Leave empty to treat this account’s whole history as part of your budget. ' +
                      'Set a date when an account arrives with history from before you tracked it.'}
                </p>
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
                          disabled={link.isPending || remoteLoading}
                          onChange={(e) => e.target.value && handleLink(e.target.value)}
                        >
                          <option value="">
                            {link.isPending
                              ? 'Linking…'
                              : remoteLoading
                                ? 'Loading accounts…'
                                : 'Select account…'}
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

            {/* Maintenance section */}
            <div className="acct-modal__section acct-modal__section--maintenance">
              <div className="acct-modal__section-title">Maintenance</div>
              <div className="acct-modal__field acct-modal__field--row acct-modal__field--scan">
                <span className="acct-modal__scan-label">
                  Find transactions that may be duplicates
                </span>
                <button
                  type="button"
                  className="acct-modal__scan-btn"
                  disabled={scanDuplicates.isPending}
                  onClick={async () => {
                    setScanResult(null)
                    const result = await scanDuplicates.mutateAsync(accountId)
                    setScanResult(result.created)
                  }}
                >
                  {scanDuplicates.isPending ? 'Scanning…' : 'Scan for Duplicates'}
                </button>
              </div>
              {scanResult !== null && (
                <p className="acct-modal__scan-result">
                  {scanResult === 0
                    ? 'No new potential duplicates found.'
                    : `Found ${scanResult} potential duplicate pair${scanResult === 1 ? '' : 's'} — review them in the transaction list.`}
                </p>
              )}
            </div>
          </div>
        </form>
      </Dialog>
      {showTypeInfo && (
        <AccountTypeInfoModal types={typeRows} onClose={() => setShowTypeInfo(false)} />
      )}
    </>
  )
}
