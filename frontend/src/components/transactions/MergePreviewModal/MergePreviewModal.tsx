import { useState } from 'react'
import { X, GitMerge } from 'lucide-react'
import { formatMoney } from '../../../utils/money'
import { formatDate } from '../../../utils/dates'
import type { Transaction } from '../../../types'
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
}: {
  txn: Transaction
  payeeMap: Map<string, string>
  categoryMap: Map<string, string>
  isSelected: boolean
  onClick: () => void
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
          <span className="merge-card__value merge-card__value--muted">{txn.import_description}</span>
        </div>
      )}
      <div className="merge-card__row">
        <span className="merge-card__label">Status</span>
        <span className={`merge-card__cleared merge-card__cleared--${txn.cleared}`}>{txn.cleared}</span>
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
  const [txn1, txn2] = transactions
  const defaultSurvivor = txn1.created_at <= txn2.created_at ? txn1.id : txn2.id
  const [survivorId, setSurvivorId] = useState<string>(defaultSurvivor)

  const survivor = survivorId === txn1.id ? txn1 : txn2
  const deleted = survivorId === txn1.id ? txn2 : txn1

  const willCopyImportId = !survivor.import_id && !!deleted.import_id
  const willCopyImportDesc = !survivor.import_description && !!deleted.import_description

  return (
    <div className="merge-modal-overlay" onClick={onCancel}>
      <div className="merge-modal" onClick={(e) => e.stopPropagation()}>
        <div className="merge-modal__header">
          <span className="merge-modal__title">
            <GitMerge size={14} />
            Merge Transactions
          </span>
          <button className="merge-modal__close" onClick={onCancel} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <p className="merge-modal__hint">
          Click a transaction to keep it. The other will be deleted.
        </p>

        <div className="merge-modal__columns">
          <TxnCard
            txn={txn1}
            payeeMap={payeeMap}
            categoryMap={categoryMap}
            isSelected={survivorId === txn1.id}
            onClick={() => setSurvivorId(txn1.id)}
          />
          <TxnCard
            txn={txn2}
            payeeMap={payeeMap}
            categoryMap={categoryMap}
            isSelected={survivorId === txn2.id}
            onClick={() => setSurvivorId(txn2.id)}
          />
        </div>

        {(willCopyImportId || willCopyImportDesc) && (
          <p className="merge-modal__note">
            Bank import data will be copied from the deleted transaction.
          </p>
        )}

        <div className="merge-modal__footer">
          <button className="merge-modal__btn merge-modal__btn--cancel" onClick={onCancel} disabled={isPending}>
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
