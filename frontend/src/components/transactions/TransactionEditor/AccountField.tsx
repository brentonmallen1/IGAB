import { useMemo } from 'react'
import { Lock } from 'lucide-react'
import { PickerField } from '../../common/PickerField/PickerField'
import { accountOptions, recentAccountsSection } from '../../../utils/accountLists'
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
 * lock glyph, and the reason underneath. A disabled picker would say
 * "not now" without ever saying why.
 *
 * The picker is the shared PickerField (Combobox on desktop, SelectionSheet
 * on a phone), so its groups — Recent, Budget accounts, Tracking — draw the
 * house group headers a native <select> could not.
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
  const options = useMemo(() => {
    const offered = accountOptions(accounts, recent.length > 0)
    // A closed account the row already sits in is not in the list. Offer it
    // anyway, or the picker would show a blank selection and the next save
    // would re-file the row somewhere it never was.
    return current?.is_closed
      ? [{ id: current.id, label: `${current.name} (closed)`, group: '' }, ...offered]
      : offered
  }, [accounts, recent.length, current])
  const pinned = useMemo(() => recentAccountsSection(recent), [recent])

  return (
    <div className="txn-editor__field">
      <span className="txn-editor__label">Account</span>
      {lockReason ? (
        <div
          className="txn-editor__input txn-editor__locked"
          aria-label={`Account: ${current?.name ?? ''}`}
        >
          <Lock size={12} aria-hidden />
          {current?.name ?? '—'}
        </div>
      ) : (
        <PickerField
          value={value || null}
          onChange={(id) => onChange(id ?? '')}
          options={options}
          pinned={pinned}
          noneLabel="Select account…"
          sheetTitle="Account"
          searchPlaceholder="Search accounts…"
          aria-label="Account"
        />
      )}
      {(lockReason || note) && <span className="txn-editor__field-note">{lockReason ?? note}</span>}
    </div>
  )
}
