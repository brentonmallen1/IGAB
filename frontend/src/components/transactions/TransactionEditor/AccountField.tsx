import { Lock } from 'lucide-react'
import type { Account } from '../../../types'

interface Props {
  /** Open accounts, as offered. A closed one the row already sits in is added
   *  back below — see the comment on that option. */
  accounts: Account[]
  /** The ones used most recently, pinned above the rest (utils/accountLists).
   *  A shortlist, never a default — nothing here is pre-selected. */
  recent: Account[]
  value: string
  onChange: (accountId: string) => void
  /** The account the row is in right now, for the locked reading and for the
   *  closed-account case. Null while a new row has not picked one. */
  current: Account | null
  /** Why the account cannot be changed (accountMove.ts), or null. */
  lockReason: string | null
  /** What changing it will cost — today, a category that cannot follow. */
  note: string | null
}

/**
 * The editor's Account field: which account this transaction is in.
 *
 * Shown for a new row that has no register to inherit from, and for any
 * existing row that may be moved. The row opened from an account register is
 * the case that used to be hidden, and the one people need — a receipt
 * scanned against the wrong account is only visible from the register it
 * landed in, so hiding the field there hid it everywhere.
 *
 * Locked rows read like the locked Cleared field beside them: the value, a
 * lock glyph, and the reason underneath. A disabled `<select>` would say
 * "not now" without ever saying why.
 */
export function AccountField({
  accounts,
  recent,
  value,
  onChange,
  current,
  lockReason,
  note,
}: Props) {
  const hasTracking = accounts.some((a) => !a.on_budget)
  const option = (a: Account, prefix = '') => (
    <option key={`${prefix}${a.id}`} value={a.id}>
      {a.name}
    </option>
  )

  return (
    <div className="txn-editor__field">
      <label className="txn-editor__label" htmlFor="txn-editor-account">
        Account
      </label>
      {lockReason ? (
        <div
          className="txn-editor__input txn-editor__locked"
          aria-label={`Account: ${current?.name ?? ''}`}
        >
          <Lock size={12} aria-hidden />
          {current?.name ?? '—'}
        </div>
      ) : (
        <select
          id="txn-editor-account"
          className="txn-editor__select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          required
          aria-label="Account"
        >
          <option value="">Select account…</option>
          {/* A closed account the row already sits in is not in the list.
              Offer it anyway, or the picker would show a blank selection and
              the next save would re-file the row somewhere it never was. */}
          {current?.is_closed && <option value={current.id}>{current.name} (closed)</option>}
          {/* Repeated below in their own group — the shortlist is a shortcut
              to the same accounts, not a different set. */}
          {recent.length > 0 && (
            <optgroup label="Recent">{recent.map((a) => option(a, 'recent'))}</optgroup>
          )}
          {hasTracking ? (
            <>
              <optgroup label="Budget accounts">
                {accounts.filter((a) => a.on_budget).map((a) => option(a))}
              </optgroup>
              <optgroup label="Tracking">
                {accounts.filter((a) => !a.on_budget).map((a) => option(a))}
              </optgroup>
            </>
          ) : (
            accounts.map((a) => option(a))
          )}
        </select>
      )}
      {(lockReason || note) && <span className="txn-editor__field-note">{lockReason ?? note}</span>}
    </div>
  )
}
