import { useEffect, useRef, useState } from 'react'
import { HelpCircle, X } from 'lucide-react'
import { useAccounts, useUpdateAccount, useScanDuplicates } from '../../api/accounts'
import {
  useLinkSimpleFINAccount,
  useUnlinkSimpleFINAccount,
  useUpdateAccountSimpleFINSettings,
  useSimpleFINConnections,
  useSimpleFINRemoteAccounts,
} from '../../api/simplefin'
import { formatSyncAge } from '../simplefin/SyncStatusIcon'
import { useFocusTrap } from '../../hooks/useFocusTrap'
import { useFormatters } from '../../hooks/useFormatters'
import { isCardAccount } from '../../utils/accountKinds'
import { useAppStore } from '../../stores/appStore'
import { useAccountTypes } from '../../api/accountTypes'
import { BUILTIN_ACCOUNT_TYPES } from '../../constants/accountTypes'
import { AccountTypeInfoModal } from './AccountTypeInfoModal'
import './AccountSettingsModal.css'
import { confirmAsync } from '../../stores/confirmStore'

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
  const { data: remoteAccounts = [] } = useSimpleFINRemoteAccounts(
    showLinkPicker ? (firstConnection?.id ?? null) : null
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
  const [note, setNote] = useState(account?.note ?? '')
  const [budgetStart, setBudgetStart] = useState(account?.budget_start_date ?? '')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [closeError, setCloseError] = useState<string | null>(null)
  const [showTypeInfo, setShowTypeInfo] = useState(false)

  const nameRef = useRef<HTMLInputElement>(null)
  const trapRef = useFocusTrap<HTMLDivElement>(onClose)

  useEffect(() => {
    if (account) {
      setName(account.name)
      setAccountType(account.account_type)
      setOnBudget(account.on_budget)
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
    // Closing moves no money. For a card that matters enough to say out
    // loud: its balance and anything reserved on its payment envelope stay
    // in the budget (the Credit cards section keeps its row, tagged Closed,
    // until both reach zero) — quietly hiding the account would read as the
    // debt or the reserve vanishing.
    const isCard = isCardAccount(account)
    const cardMessage =
      account.balance !== 0
        ? `This card's balance is ${formatMoney(account.balance)}. Closing moves no money — the balance and anything reserved to pay it stay in the budget's Credit cards section until both reach zero.`
        : `Closing moves no money — anything still reserved to pay this card keeps reducing Ready to Assign until you move it out or record a payment.`
    const ok = await confirmAsync({
      title: `${action === 'close' ? 'Close' : 'Reopen'} this account?`,
      confirmLabel: action === 'close' ? 'Close account' : 'Reopen account',
      ...(action === 'close' && isCard ? { message: cardMessage } : {}),
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
    <div className="acct-modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={trapRef}
        tabIndex={-1}
        className="acct-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="acct-modal-title"
      >
        <div className="acct-modal__header">
          <span id="acct-modal-title" className="acct-modal__title">
            Account Settings
          </span>
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
                  onChange={(e) => setAccountType(e.target.value)}
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
              className="acct-modal__btn acct-modal__btn--save"
              disabled={updateAccount.isPending || !name.trim()}
            >
              {updateAccount.isPending ? 'Saving…' : 'Save'}
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
