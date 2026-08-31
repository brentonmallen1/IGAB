import { useState } from 'react'
import { X, GitMerge } from 'lucide-react'
import { useFormatters } from '../../../hooks/useFormatters'
import type { Transaction } from '../../../types'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import './MergePreviewModal.css'

interface Props {
  transactions: [Transaction, Transaction]
  payeeMap: Map<string, string>
  categoryMap: Map<string, string>
  onConfirm: (survivorId?: string) => void
  onCancel: () => void
  isPending: boolean
}

function TxnCard({
  txn,
  payeeMap,
  categoryMap,
  isSelected,
  onClick,
  formatMoney,
  formatDate,
}: {
  txn: Transaction
  payeeMap: Map<string, string>
  categoryMap: Map<string, string>
  isSelected: boolean
  onClick?: () => void
  formatMoney: (amount: number) => string
  formatDate: (dateStr: string) => string
}) {
  const payeeName = txn.payee_id ? (payeeMap.get(txn.payee_id) ?? '—') : '—'
  const categoryName = txn.category_id ? (categoryMap.get(txn.category_id) ?? '—') : '—'
  const outflow = txn.amount < 0 ? Math.abs(txn.amount) : 0
  const inflow = txn.amount >= 0 ? txn.amount : 0

  return (
    <button
      type="button"
      className={`merge-card ${isSelected ? 'merge-card--selected' : ''}`}
      onClick={onClick}
    >
      {isSelected && <span className="merge-card__badge">Keep</span>}
      <div className="merge-card__row">
        <span className="merge-card__label">Date</span>
        <span>{formatDate(txn.date)}</span>
      </div>
      <div className="merge-card__row">
        <span className="merge-card__label">Amount</span>
        <span className={txn.amount < 0 ? 'txn-outflow' : 'txn-inflow'}>
          {outflow > 0 ? `-${formatMoney(outflow)}` : formatMoney(inflow)}
        </span>
      </div>
      <div className="merge-card__row">
        <span className="merge-card__label">Payee</span>
        <span className="merge-card__value">{payeeName}</span>
      </div>
      <div className="merge-card__row">
        <span className="merge-card__label">Category</span>
        <span className="merge-card__value">{categoryName}</span>
      </div>
      {txn.memo && (
        <div className="merge-card__row">
          <span className="merge-card__label">Memo</span>
          <span className="merge-card__value merge-card__value--muted">{txn.memo}</span>
        </div>
      )}
      {txn.import_description && (
        <div className="merge-card__row">
          <span className="merge-card__label">Bank desc</span>
          <span className="merge-card__value merge-card__value--muted">
            {txn.import_description}
          </span>
        </div>
      )}
      <div className="merge-card__row">
        <span className="merge-card__label">Status</span>
        <span className={`merge-card__cleared merge-card__cleared--${txn.cleared}`}>
          {txn.cleared}
        </span>
      </div>
    </button>
  )
}

export function MergePreviewModal({
  transactions,
  payeeMap,
  categoryMap,
  onConfirm,
  onCancel,
  isPending,
}: Props) {
  const { formatMoney, formatDate } = useFormatters()
  const [txn1, txn2] = transactions
  const reconciledTxn =
    txn1.cleared === 'reconciled' ? txn1 : txn2.cleared === 'reconciled' ? txn2 : null
  const defaultSurvivor =
    reconciledTxn?.id ?? (txn1.created_at <= txn2.created_at ? txn1.id : txn2.id)
  const [survivorId, setSurvivorId] = useState<string>(defaultSurvivor)
  const trapRef = useFocusTrap<HTMLDivElement>(onCancel)

  const survivor = survivorId === txn1.id ? txn1 : txn2
  const deleted = survivorId === txn1.id ? txn2 : txn1

  const willCopyImportId = !survivor.import_id && !!deleted.import_id
  const willCopyImportDesc = !survivor.import_description && !!deleted.import_description
  const willCopySyncId = !survivor.sync_id && !!deleted.sync_id

  return (
    <div className="merge-modal-overlay" onClick={onCancel}>
      <div
        ref={trapRef}
        tabIndex={-1}
        className="merge-modal"
        role="dialog"
        aria-modal
        aria-labelledby="merge-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="merge-modal__header">
          <span id="merge-modal-title" className="merge-modal__title">
            <GitMerge size={14} />
            Merge Transactions
          </span>
          <button className="merge-modal__close" onClick={onCancel} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <p className="merge-modal__hint">
          {reconciledTxn
            ? 'The reconciled transaction will always be kept.'
            : 'Click a transaction to keep it. The other is removed — but nothing it has is lost: a memo, category, payee, receipt or bank details the kept one lacks carry over.'}
        </p>

        <div className="merge-modal__columns">
          <TxnCard
            txn={txn1}
            payeeMap={payeeMap}
            categoryMap={categoryMap}
            isSelected={survivorId === txn1.id}
            onClick={reconciledTxn ? undefined : () => setSurvivorId(txn1.id)}
            formatMoney={formatMoney}
            formatDate={formatDate}
          />
          <TxnCard
            txn={txn2}
            payeeMap={payeeMap}
            categoryMap={categoryMap}
            isSelected={survivorId === txn2.id}
            onClick={reconciledTxn ? undefined : () => setSurvivorId(txn2.id)}
            formatMoney={formatMoney}
            formatDate={formatDate}
          />
        </div>

        {(willCopyImportId || willCopyImportDesc || willCopySyncId) && (
          <p className="merge-modal__note">
            Bank import data will be copied from the deleted transaction.
          </p>
        )}

        <div className="merge-modal__footer">
          <button
            className="merge-modal__btn merge-modal__btn--cancel"
            onClick={onCancel}
            disabled={isPending}
          >
            Cancel
          </button>
          <button
            className="merge-modal__btn merge-modal__btn--confirm"
            onClick={() => onConfirm(survivorId)}
            disabled={isPending}
          >
            {isPending ? 'Merging…' : 'Confirm Merge'}
          </button>
        </div>
      </div>
    </div>
  )
}
