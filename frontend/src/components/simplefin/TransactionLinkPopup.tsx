import { useState } from 'react'
import { Link2, X, Check, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { formatMoney } from '../../utils/money'
import { formatDate } from '../../utils/dates'
import type { Transaction, TransactionMatch } from '../../types'
import './TransactionLinkPopup.css'

interface LinkedTransactionDetail {
  transaction: Transaction
  match: TransactionMatch | null
}

interface Props {
  transaction: Transaction
  budgetId: string
  onClose: () => void
  onAccept?: (matchId: string) => void
  onReject?: (matchId: string) => void
}

function useLinkedTransaction(linkedId: string | null) {
  return useQuery({
    queryKey: ['transaction', linkedId],
    queryFn: async () => {
      const { data } = await apiClient.get<Transaction>(`/transactions/${linkedId}`)
      return data
    },
    enabled: !!linkedId,
    staleTime: 60_000,
  })
}

function useMatchForTransactions(synced_id: string | null, manual_id: string | null) {
  return useQuery({
    queryKey: ['transaction-link-match', synced_id, manual_id],
    queryFn: async () => {
      // Find the match record for these two transactions
      const { data } = await apiClient.get<TransactionMatch[]>('/simplefin/matches', {
        params: { budget_id: 'current' },
      })
      return data.find(
        (m) =>
          (m.synced_transaction_id === synced_id && m.manual_transaction_id === manual_id) ||
          (m.synced_transaction_id === manual_id && m.manual_transaction_id === synced_id),
      ) ?? null
    },
    enabled: !!(synced_id && manual_id),
    staleTime: 15_000,
  })
}

function ConfidenceMeter({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 90 ? 'var(--color-success)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-danger)'
  return (
    <div className="link-popup__confidence">
      <span className="link-popup__confidence-label">Match confidence</span>
      <div className="link-popup__confidence-bar">
        <div
          className="link-popup__confidence-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="link-popup__confidence-pct">{pct}%</span>
    </div>
  )
}

export function TransactionLinkIcon({
  transaction,
  budgetId,
  onAccept,
  onReject,
}: {
  transaction: Transaction
  budgetId: string
  onAccept?: (matchId: string) => void
  onReject?: (matchId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const visible = transaction.has_sync_source || !!transaction.linked_transaction_id
  if (!visible) return null

  const title = transaction.has_sync_source
    ? 'Matched with bank import'
    : transaction.link_confidence
      ? `Linked to manually entered transaction (${Math.round(transaction.link_confidence * 100)}% confidence)`
      : 'Linked to manually entered transaction'

  return (
    <span className="txn-link-indicator">
      <button
        className="txn-link-btn"
        onClick={(e) => {
          e.stopPropagation()
          if (transaction.linked_transaction_id) setOpen(true)
        }}
        title={title}
        aria-label="View linked transaction"
        style={transaction.has_sync_source && !transaction.linked_transaction_id ? { cursor: 'default' } : undefined}
      >
        <Link2 size={11} />
      </button>
      {open && transaction.linked_transaction_id && (
        <TransactionLinkPopup
          transaction={transaction}
          budgetId={budgetId}
          onClose={() => setOpen(false)}
          onAccept={onAccept}
          onReject={onReject}
        />
      )}
    </span>
  )
}

export function TransactionLinkPopup({
  transaction,
  budgetId: _budgetId,
  onClose,
  onAccept,
  onReject,
}: Props) {
  const { data: linked, isLoading } = useLinkedTransaction(transaction.linked_transaction_id)

  const isSynced = !!transaction.import_id
  const syncedTxn = isSynced ? transaction : linked
  const manualTxn = isSynced ? linked : transaction

  return (
    <div className="link-popup-overlay" onClick={onClose}>
      <div className="link-popup" onClick={(e) => e.stopPropagation()}>
        <div className="link-popup__header">
          <span className="link-popup__title">
            <Link2 size={14} />
            Linked Transactions
          </span>
          <button className="link-popup__close" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        {transaction.link_confidence != null && (
          <ConfidenceMeter score={transaction.link_confidence} />
        )}

        <div className="link-popup__columns">
          <div className="link-popup__col">
            <div className="link-popup__col-label">From Bank (synced)</div>
            {syncedTxn ? (
              <TransactionDetail txn={syncedTxn} />
            ) : (
              <span className="link-popup__loading">
                {isLoading ? <RefreshCw size={12} className="spin" /> : '—'}
              </span>
            )}
          </div>
          <div className="link-popup__divider" />
          <div className="link-popup__col">
            <div className="link-popup__col-label">Manually entered</div>
            {manualTxn ? (
              <TransactionDetail txn={manualTxn} />
            ) : (
              <span className="link-popup__loading">
                {isLoading ? <RefreshCw size={12} className="spin" /> : '—'}
              </span>
            )}
          </div>
        </div>

        <p className="link-popup__hint">
          The manually entered transaction's category and payee are used. Click the link icon on
          either transaction to edit or remove the link.
        </p>
      </div>
    </div>
  )
}

function TransactionDetail({ txn }: { txn: Transaction }) {
  const outflow = txn.amount < 0 ? Math.abs(txn.amount) : 0
  const inflow = txn.amount > 0 ? txn.amount : 0
  return (
    <div className="link-popup__txn-detail">
      <div className="link-popup__txn-row">
        <span className="link-popup__txn-label">Date</span>
        <span>{formatDate(txn.date)}</span>
      </div>
      <div className="link-popup__txn-row">
        <span className="link-popup__txn-label">Amount</span>
        <span className={txn.amount < 0 ? 'txn-outflow' : 'txn-inflow'}>
          {outflow > 0 ? `-${formatMoney(outflow)}` : formatMoney(inflow)}
        </span>
      </div>
      <div className="link-popup__txn-row">
        <span className="link-popup__txn-label">Status</span>
        <span className={`link-popup__cleared link-popup__cleared--${txn.cleared}`}>
          {txn.cleared}
        </span>
      </div>
      {txn.memo && (
        <div className="link-popup__txn-row">
          <span className="link-popup__txn-label">Memo</span>
          <span className="link-popup__txn-memo">{txn.memo}</span>
        </div>
      )}
    </div>
  )
}
