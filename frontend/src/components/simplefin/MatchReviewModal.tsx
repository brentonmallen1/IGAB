import { useState } from 'react'
import { X, Link2, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { useAcceptMatch, useRejectMatch } from '../../api/simplefin'
import { formatMoney } from '../../utils/money'
import { formatDate } from '../../utils/dates'
import type { Transaction, TransactionMatch } from '../../types'
import './MatchReviewModal.css'

function useTransaction(id: string | null) {
  return useQuery({
    queryKey: ['transaction', id],
    queryFn: async () => {
      const { data } = await apiClient.get<Transaction>(`/transactions/${id}`)
      return data
    },
    enabled: !!id,
    staleTime: 60_000,
  })
}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 90 ? 'var(--color-success)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-danger)'
  return (
    <div className="match-modal__confidence">
      <span className="match-modal__confidence-label">Match confidence</span>
      <div className="match-modal__confidence-bar">
        <div className="match-modal__confidence-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="match-modal__confidence-pct" style={{ color }}>{pct}%</span>
    </div>
  )
}

function TxnDetail({ txn, label }: { txn: Transaction; label: string }) {
  const outflow = txn.amount < 0 ? Math.abs(txn.amount) : 0
  const inflow = txn.amount >= 0 ? txn.amount : 0
  return (
    <div className="match-modal__col">
      <div className="match-modal__col-label">{label}</div>
      <div className="match-modal__txn-detail">
        <div className="match-modal__txn-row">
          <span className="match-modal__txn-key">Date</span>
          <span>{formatDate(txn.date)}</span>
        </div>
        <div className="match-modal__txn-row">
          <span className="match-modal__txn-key">Amount</span>
          <span className={txn.amount < 0 ? 'txn-outflow' : 'txn-inflow'}>
            {outflow > 0 ? `-${formatMoney(outflow)}` : formatMoney(inflow)}
          </span>
        </div>
        <div className="match-modal__txn-row">
          <span className="match-modal__txn-key">Status</span>
          <span className={`match-modal__cleared match-modal__cleared--${txn.cleared}`}>{txn.cleared}</span>
        </div>
        {txn.import_description && (
          <div className="match-modal__txn-row">
            <span className="match-modal__txn-key">Bank desc</span>
            <span className="match-modal__txn-desc">{txn.import_description}</span>
          </div>
        )}
        {txn.memo && (
          <div className="match-modal__txn-row">
            <span className="match-modal__txn-key">Memo</span>
            <span className="match-modal__txn-desc">{txn.memo}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function MatchCard({
  match,
  onAccepted,
  onRejected,
}: {
  match: TransactionMatch
  onAccepted: () => void
  onRejected: () => void
}) {
  const { data: syncedTxn, isLoading: loadingS } = useTransaction(match.synced_transaction_id)
  const { data: manualTxn, isLoading: loadingM } = useTransaction(match.manual_transaction_id)
  const acceptMatch = useAcceptMatch()
  const rejectMatch = useRejectMatch()

  const loading = loadingS || loadingM

  async function handleAccept() {
    await acceptMatch.mutateAsync(match.id)
    onAccepted()
  }

  async function handleReject() {
    await rejectMatch.mutateAsync(match.id)
    onRejected()
  }

  return (
    <div className="match-modal__card">
      <ConfidenceBar score={match.confidence_score} />

      {loading ? (
        <div className="match-modal__loading">
          <RefreshCw size={16} className="spin" />
        </div>
      ) : (
        <div className="match-modal__columns">
          {syncedTxn && <TxnDetail txn={syncedTxn} label="From bank (synced)" />}
          <div className="match-modal__divider" />
          {manualTxn && <TxnDetail txn={manualTxn} label="Manually entered" />}
        </div>
      )}

      <p className="match-modal__hint">
        Accepting keeps your manual entry (with its category and payee) and removes the bank duplicate.
      </p>

      <div className="match-modal__actions">
        <button
          className="match-modal__btn match-modal__btn--accept"
          onClick={handleAccept}
          disabled={acceptMatch.isPending || rejectMatch.isPending}
        >
          Accept link
        </button>
        <button
          className="match-modal__btn match-modal__btn--reject"
          onClick={handleReject}
          disabled={acceptMatch.isPending || rejectMatch.isPending}
        >
          Keep separate
        </button>
      </div>
    </div>
  )
}

interface Props {
  matches: TransactionMatch[]
  onClose: () => void
}

export function MatchReviewModal({ matches, onClose }: Props) {
  const [idx, setIdx] = useState(0)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const pending = matches.filter((m) => !dismissed.has(m.id))
  const current = pending[idx] ?? pending[0]

  function handleDismiss(matchId: string) {
    const next = new Set(dismissed).add(matchId)
    setDismissed(next)
    const remaining = matches.filter((m) => !next.has(m.id))
    if (remaining.length === 0) {
      onClose()
    } else {
      setIdx(Math.min(idx, remaining.length - 1))
    }
  }

  if (!current) return null

  return (
    <div className="match-modal-overlay" onClick={onClose}>
      <div className="match-modal" onClick={(e) => e.stopPropagation()}>
        <div className="match-modal__header">
          <span className="match-modal__title">
            <Link2 size={14} />
            Review Possible Duplicate
          </span>
          <div className="match-modal__header-right">
            {pending.length > 1 && (
              <span className="match-modal__counter">{idx + 1} / {pending.length}</span>
            )}
            <button className="match-modal__close" onClick={onClose} aria-label="Close">
              <X size={14} />
            </button>
          </div>
        </div>

        <MatchCard
          key={current.id}
          match={current}
          onAccepted={() => handleDismiss(current.id)}
          onRejected={() => handleDismiss(current.id)}
        />

        {pending.length > 1 && (
          <div className="match-modal__nav">
            <button
              className="match-modal__nav-btn"
              onClick={() => setIdx((i) => Math.max(0, i - 1))}
              disabled={idx === 0}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <button
              className="match-modal__nav-btn"
              onClick={() => setIdx((i) => Math.min(pending.length - 1, i + 1))}
              disabled={idx === pending.length - 1}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
