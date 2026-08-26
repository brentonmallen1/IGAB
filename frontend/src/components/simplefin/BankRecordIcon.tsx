import { Landmark, Link2 } from 'lucide-react'
import { Tooltip } from '../common/Tooltip/Tooltip'
import type { Transaction } from '../../types'
import { useFormatters } from '../../hooks/useFormatters'
import './BankRecordIcon.css'

/**
 * Marks a row the bank supplied, and carries what the bank actually
 * reported — its posted date, amount and payee string — in the tooltip.
 * Those values can drift from the ledger ones the user edits, and the
 * editor is otherwise the only place they're visible.
 */
export function BankRecordIcon({ transaction }: { transaction: Transaction }) {
  const { formatMoney, formatDate } = useFormatters()

  if (!transaction.has_sync_source && !transaction.sync_source) return null

  // A row the user entered (by hand, from a schedule, or via the AI paths)
  // that the bank later matched reads differently from one the bank wrote:
  // the first is the user's record with the bank's confirmation attached.
  // `created_via` is the origin stamp (backend Transaction.created_via);
  // null is unknown — rows older than the stamp — and reads as the bank's.
  const enteredByUser =
    transaction.created_via != null && transaction.created_via !== 'sync' &&
    transaction.created_via !== 'import'
  const bankPayee = transaction.bank_payee ?? transaction.import_description
  const lines = [
    enteredByUser
      ? `Entered by you${transaction.created_at ? ` ${formatDate(transaction.created_at.slice(0, 10))}` : ''}, matched to your bank`
      : 'From your bank',
    transaction.bank_posted_date ? `Posted ${formatDate(transaction.bank_posted_date)}` : null,
    transaction.bank_amount != null ? `Amount ${formatMoney(transaction.bank_amount)}` : null,
    // The bank's posted amount replaced what was entered — say so, and say
    // what it was. Home: Transaction.entered_amount.
    transaction.entered_amount != null
      ? `Amount updated from ${formatMoney(transaction.entered_amount)} when the bank posted`
      : null,
    bankPayee ? `Payee ${bankPayee}` : null,
  ].filter(Boolean) as string[]

  return (
    <Tooltip
      content={lines.map((line) => (
        <div key={line}>{line}</div>
      ))}
    >
      <span className="bank-record-icon" role="img" aria-label={lines.join('. ')}>
        {enteredByUser ? <Link2 size={11} /> : <Landmark size={11} />}
      </span>
    </Tooltip>
  )
}
