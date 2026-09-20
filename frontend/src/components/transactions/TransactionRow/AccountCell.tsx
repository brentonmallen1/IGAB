import { useMemo } from 'react'
import { useAccountMove } from '../../../hooks/useAccountMove'
import { accountLockReason } from '../TransactionEditor/accountMove'
import { Combobox, type ComboboxOption } from '../../common/Combobox/Combobox'
import type { Account, Transaction } from '../../../types'

/**
 * The register's Account column — read in every register that shows it, and
 * editable in place like every other column beside it.
 *
 * Only the all-accounts register draws this column, which is also the only
 * view where the question comes up: a receipt scanned against the wrong card
 * is invisible from the register it landed in, and obvious here, where both
 * accounts are on screen. Until this cell was editable, noticing it here and
 * fixing it meant opening the editor — the one column of the row that made
 * you leave the row.
 *
 * Whether a row MAY move is `accountMove.ts`, shared with the editor's
 * Account field so the two surfaces cannot disagree; the server's own rule
 * (`domain/account_move.py`) refuses regardless of what either offers.
 */

export interface AccountCellLock {
  /** Why this row cannot move, for the cell's tooltip; null when it can. */
  reason: string | null
  /** The column is drawn AND unlocked — what Tab needs to know. */
  movable: boolean
}

/**
 * The lock, asked once and used twice: the cell renders from it, and the
 * row's Tab order needs the same answer. Exported so `fieldOrder` gets a
 * fact rather than a second copy of the rule.
 */
export function accountCellLock(txn: Transaction, hasColumn: boolean): AccountCellLock {
  const reason = accountLockReason({
    isReconciled: txn.cleared === 'reconciled',
    isBankFed: !!txn.sync_id,
    // The register lists parent rows; a split's lines are not rows here.
    isSplitLine: false,
  })
  return { reason, movable: hasColumn && reason === null }
}

interface Props {
  transaction: Transaction
  budgetId: string
  /** Open accounts — every one of them a legal destination. */
  accounts: Account[]
  /** Undefined in a single account's register, which draws no column —
   *  there, the account is the register. */
  label: string | undefined
  /** CSS color value for the account's identity dot. */
  color?: string
  lock: AccountCellLock
  isEditing: boolean
  /** Inline cell editing is desktop-only, as it is for every column. */
  isMobile: boolean
  onStartEdit: () => void
  onStopEdit: () => void
  onTabOut: (direction: 1 | -1) => void
}

export function AccountCell({
  transaction,
  budgetId,
  accounts,
  label,
  color,
  lock,
  isEditing,
  isMobile,
  onStartEdit,
  onStopEdit,
  onTabOut,
}: Props) {
  const commitMove = useAccountMove(budgetId)
  const editable = lock.movable && !isMobile

  const options = useMemo<ComboboxOption[]>(
    // `useAccounts` leaves closed accounts out and the server refuses to move
    // a row into one, so every option here is somewhere the row may go.
    () => accounts.map((a) => ({ id: a.id, label: a.name, group: a.on_budget ? '' : 'Tracking' })),
    [accounts]
  )

  function move(id: string | null) {
    // The no-op skip and the refusal message are useAccountMove's — the AI
    // review list commits the same move and must do it the same way.
    commitMove(transaction, id)
    onStopEdit()
  }

  if (label === undefined) return null

  return (
    <div
      className="txn-col txn-col--account txn-text-clip"
      title={lock.reason ?? label}
      onClick={() => editable && onStartEdit()}
    >
      {isEditing && editable ? (
        <Combobox
          value={transaction.account_id}
          options={options}
          onChange={move}
          placeholder="Move to account…"
          autoFocus
          onBlurClose={onStopEdit}
          onTabOut={onTabOut}
        />
      ) : (
        <>
          <span
            className="txn-account-dot"
            style={color ? { backgroundColor: color } : undefined}
            aria-hidden
          />
          <span className="txn-cell-text">{label}</span>
        </>
      )}
    </div>
  )
}
