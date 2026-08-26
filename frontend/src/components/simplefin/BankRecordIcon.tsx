import { Landmark } from 'lucide-react'
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

  const bankPayee = transaction.bank_payee ?? transaction.import_description
  const lines = [
    'From your bank',
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
    <span className="bank-record-icon" title={lines.join('\n')} aria-label={lines.join('. ')}>
      <Landmark size={11} />
    </span>
  )
}
