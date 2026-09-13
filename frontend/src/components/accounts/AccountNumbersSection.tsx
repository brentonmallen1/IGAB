import { useState } from 'react'
import { Copy, Eye, EyeOff } from 'lucide-react'
import toast from 'react-hot-toast'
import { useSimpleFINConfig } from '../../api/simplefin'
import { fetchAccountSecrets, type AccountSecrets } from '../../api/accounts'
import { apiErrorMessage } from '../../api/client'
import type { Account } from '../../types'

interface Props {
  account: Account | undefined
  onSave: (patch: {
    account_number?: string | null
    routing_number?: string | null
  }) => Promise<unknown>
}

/**
 * Routing and account numbers, encrypted at rest with the same key bank sync
 * uses. Shown masked; the eye fetches the numbers on demand and the copy
 * button puts one on the clipboard. Hidden with a hint when the server has
 * no key — there is nowhere safe to keep them then.
 */
export function AccountNumbersSection({ account, onSave }: Props) {
  const { data: config } = useSimpleFINConfig()
  const [revealed, setRevealed] = useState<AccountSecrets | null>(null)
  const [editing, setEditing] = useState(false)
  const [accountNumber, setAccountNumber] = useState('')
  const [routingNumber, setRoutingNumber] = useState('')
  const [busy, setBusy] = useState(false)

  if (!account) return null
  if (config && !config.configured) {
    return (
      <div className="dialog-form__field">
        <span>Account numbers</span>
        <p className="dialog-form__hint">
          Not available: this server has no encryption key, so there is nowhere safe to keep them.
          Set SIMPLEFIN_ENCRYPTION_KEY to enable both bank sync and this.
        </p>
      </div>
    )
  }

  const hasAny = !!account.account_number_last4 || !!account.has_routing_number

  async function reveal() {
    try {
      setRevealed(await fetchAccountSecrets(account!.id))
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not read the numbers'))
    }
  }

  async function copy(value: string | null, what: string) {
    if (!value) return
    try {
      await navigator.clipboard.writeText(value)
      toast.success(`${what} copied`)
    } catch {
      toast.error('Clipboard is not available here')
    }
  }

  async function save() {
    if (busy) return
    setBusy(true)
    try {
      await onSave({
        account_number: accountNumber.trim() || null,
        routing_number: routingNumber.trim() || null,
      })
      setEditing(false)
      setRevealed(null)
      setAccountNumber('')
      setRoutingNumber('')
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not save the numbers'))
    } finally {
      setBusy(false)
    }
  }

  function onEditorKeyDown(e: React.KeyboardEvent) {
    if (e.key !== 'Enter' || !(e.target instanceof HTMLInputElement)) return
    // preventDefault stops the implicit submission of the enclosing form.
    e.preventDefault()
    void save()
  }

  const masked = (value: string | null | undefined, known: boolean, tail?: string | null) =>
    revealed ? (value ?? '—') : known ? (tail ? `••••${tail}` : '•••••••••') : '—'

  return (
    <div className="dialog-form__field">
      <span>Account numbers</span>
      {editing ? (
        // Not a <form>: this sits inside the Account Settings form, and a form
        // nested in a form is dropped by the parser — its Enter and its Save
        // then submitted the settings instead. Enter is handled here, and
        // stopped, so it saves the numbers and only the numbers.
        <div
          className="acct-modal__numbers-editor"
          role="group"
          aria-label="Edit account numbers"
          onKeyDown={onEditorKeyDown}
        >
          <input
            value={routingNumber}
            onChange={(e) => setRoutingNumber(e.target.value)}
            placeholder="Routing number"
            aria-label="Routing number"
            autoComplete="off"
          />
          <input
            value={accountNumber}
            onChange={(e) => setAccountNumber(e.target.value)}
            placeholder="Account number"
            aria-label="Account number"
            autoComplete="off"
          />
          <div className="acct-modal__numbers-actions">
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              disabled={busy}
              onClick={save}
            >
              {busy ? 'Saving…' : 'Save numbers'}
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
          <p className="dialog-form__hint">
            Stored encrypted; leave both blank and save to remove them. They never appear in the
            activity log.
          </p>
        </div>
      ) : hasAny ? (
        <div className="acct-modal__numbers">
          <div className="acct-modal__numbers-row">
            <span className="acct-modal__numbers-label">Routing</span>
            <code className="acct-modal__numbers-value">
              {masked(revealed?.routing_number, !!account.has_routing_number)}
            </code>
            {revealed?.routing_number && (
              <button
                type="button"
                className="acct-modal__icon-btn"
                onClick={() => copy(revealed.routing_number, 'Routing number')}
                aria-label="Copy routing number"
              >
                <Copy size={14} />
              </button>
            )}
          </div>
          <div className="acct-modal__numbers-row">
            <span className="acct-modal__numbers-label">Account</span>
            <code className="acct-modal__numbers-value">
              {masked(
                revealed?.account_number,
                !!account.account_number_last4,
                account.account_number_last4
              )}
            </code>
            {revealed?.account_number && (
              <button
                type="button"
                className="acct-modal__icon-btn"
                onClick={() => copy(revealed.account_number, 'Account number')}
                aria-label="Copy account number"
              >
                <Copy size={14} />
              </button>
            )}
          </div>
          <div className="acct-modal__numbers-actions">
            <button
              type="button"
              className="acct-modal__icon-btn"
              onClick={() => (revealed ? setRevealed(null) : reveal())}
              aria-label={revealed ? 'Hide numbers' : 'Show numbers'}
              title={revealed ? 'Hide' : 'Show'}
            >
              {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={() => setEditing(true)}
            >
              Change
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="dialog-btn dialog-btn--secondary acct-modal__start"
          onClick={() => setEditing(true)}
        >
          Add routing / account number…
        </button>
      )}
    </div>
  )
}
