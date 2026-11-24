import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, RefreshCw, AlertTriangle } from 'lucide-react'
import { apiErrorMessage } from '../../api/client'
import { useAcceptMatch, useRejectMatch } from '../../api/simplefin'
import { useAccounts } from '../../api/accounts'
import { usePayees } from '../../api/payees'
import { useFormatters } from '../../hooks/useFormatters'
import { useCategoryLabels } from '../../hooks/useCategoryLabels'
import type { MergeKeep, Transaction, TransactionMatch } from '../../types'
import { useTransaction } from '../../api/transactions'
import { Dialog } from '../common/Dialog/Dialog'
import { MergePair } from '../transactions/MergePair/MergePair'
import { pairLabels } from '../transactions/MergePair/mergePicks'
import { useMergeResult } from '../transactions/MergePair/useMergeResult'
// After Dialog, so its one-class variations are declared after the shared ones.
import './MatchReviewModal.css'

/** One object for "no picks", so the preview's query key does not change on
 *  every render. */
const NO_PICKS: MergeKeep = {}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 90 ? 'var(--color-success)' : pct >= 70 ? 'var(--color-warning)' : 'var(--color-danger)'
  return (
    <div className="match-modal__confidence">
      <span className="match-modal__confidence-label">Match confidence</span>
      <div className="match-modal__confidence-bar">
        <div
          className="match-modal__confidence-fill"
          style={{ transform: `scaleX(${score})`, background: color }}
        />
      </div>
      <span className="match-modal__confidence-pct" style={{ color }}>
        {pct}%
      </span>
    </div>
  )
}

/** Days between the two rows on the bank's posting date where each has one. */
function postedGapDays(a: Transaction, b: Transaction): number {
  const da = new Date(a.bank_posted_date ?? a.date).getTime()
  const db = new Date(b.bank_posted_date ?? b.date).getTime()
  return Math.round(Math.abs(da - db) / 86_400_000)
}

function MatchCard({
  match,
  budgetId,
  keep,
  onKeepChange,
  onReady,
}: {
  match: TransactionMatch
  budgetId: string | null
  keep: MergeKeep
  onKeepChange: (keep: MergeKeep) => void
  /** Whether the server has said what accepting would leave, and not no. */
  onReady: (ready: boolean) => void
}) {
  const { formatMoney } = useFormatters()
  const { data: syncedTxn, isLoading: loadingS } = useTransaction(match.synced_transaction_id)
  const { data: manualTxn, isLoading: loadingM } = useTransaction(match.manual_transaction_id)
  const { data: payees = [] } = usePayees(budgetId)
  const { data: accounts = [] } = useAccounts(budgetId)

  const payeeMap = new Map(payees.map((p) => [p.id, p.name]))
  const categoryLabels = useCategoryLabels(budgetId)

  // The result is the server's (`MergePair`): this dialog used to compose
  // its own — a second implementation of the merge, which drew the entered
  // row's date and category whichever row the merge actually kept.
  const pair = syncedTxn && manualTxn ? ([syncedTxn.id, manualTxn.id] as const) : null
  const result = useMergeResult(budgetId, pair, keep)
  useEffect(() => onReady(result.ready), [result.ready, onReady])

  const loading = loadingS || loadingM

  return (
    <div className="match-modal__card">
      <ConfidenceBar score={match.confidence_score} />

      {loading ? (
        <div className="match-modal__loading">
          <RefreshCw size={16} className="spin" />
        </div>
      ) : (
        syncedTxn &&
        manualTxn && (
          <>
            {(manualTxn.cleared === 'reconciled' || syncedTxn.cleared === 'reconciled') && (
              <div className="match-modal__callout" role="note">
                <AlertTriangle size={13} aria-hidden />
                <span>
                  One of these is <strong>reconciled</strong>. Accepting keeps the reconciled row
                  and removes the other, so only accept if they are the same purchase.
                </span>
              </div>
            )}

            {postedGapDays(syncedTxn, manualTxn) >= 2 && (
              <div className="match-modal__callout" role="note">
                <AlertTriangle size={13} aria-hidden />
                <span>
                  These posted <strong>{postedGapDays(syncedTxn, manualTxn)} days apart</strong>. A
                  charge that repeats — the same coffee every week — looks like this; check the
                  dates before accepting.
                </span>
              </div>
            )}

            {syncedTxn.amount !== manualTxn.amount && (
              <div className="match-modal__callout" role="note">
                <AlertTriangle size={13} aria-hidden />
                <span>
                  The amounts differ: <strong>{formatMoney(Math.abs(syncedTxn.amount))}</strong> and{' '}
                  <strong>{formatMoney(Math.abs(manualTxn.amount))}</strong>. Check they are the
                  same purchase before accepting.
                </span>
              </div>
            )}

            <MergePair
              rows={[syncedTxn, manualTxn]}
              labels={pairLabels(syncedTxn, manualTxn)}
              preview={result.preview}
              refusal={result.refusal}
              keep={keep}
              onKeepChange={onKeepChange}
              payeeMap={payeeMap}
              categoryLabels={categoryLabels}
              accountOnBudget={
                accounts.find((acct) => acct.id === manualTxn.account_id)?.on_budget ?? true
              }
            />
          </>
        )
      )}
    </div>
  )
}

interface Props {
  matches: TransactionMatch[]
  budgetId: string | null
  onClose: () => void
  initialMatchId?: string
  /** Answer every pair in the queue "keep separate" at once. Offered by a
   *  caller that owns one account's queue (the account page); the caller
   *  does the work and closes this. */
  onKeepAllSeparate?: () => void
  keepingAllSeparate?: boolean
}

export function MatchReviewModal({
  matches,
  budgetId,
  onClose,
  initialMatchId,
  onKeepAllSeparate,
  keepingAllSeparate = false,
}: Props) {
  const [idx, setIdx] = useState(() => {
    if (!initialMatchId) return 0
    const i = matches.findIndex((m) => m.id === initialMatchId)
    return i >= 0 ? i : 0
  })
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  // The picks belong to the pair on screen: moving on starts the next one
  // from the defaults, whichever way the move happened.
  const [picks, setPicks] = useState<{ matchId: string; keep: MergeKeep } | null>(null)
  const [ready, setReady] = useState(false)
  const acceptMatch = useAcceptMatch(budgetId)
  const rejectMatch = useRejectMatch()
  const deciding = acceptMatch.isPending || rejectMatch.isPending || keepingAllSeparate

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
  const keep = picks?.matchId === current.id ? picks.keep : NO_PICKS

  async function decide(accept: boolean) {
    const id = current.id
    // A refused accept used to reject the awaited promise with nothing
    // catching it: the button did nothing and nothing said why. The refusal
    // is the one thing the user needs to read.
    setError(null)
    try {
      if (accept) await acceptMatch.mutateAsync({ matchId: id, keep })
      else await rejectMatch.mutateAsync(id)
    } catch (err) {
      setError(
        apiErrorMessage(err, accept ? 'These could not be merged' : 'Could not keep these separate')
      )
      return
    }
    handleDismiss(id)
  }

  return (
    <Dialog
      // The queue position moves into the title: Dialog takes a string, and
      // "3 of 7" belongs with the name of the thing being counted anyway.
      title={
        pending.length > 1
          ? `Review Possible Duplicate — ${idx + 1} of ${pending.length}`
          : 'Review Possible Duplicate'
      }
      onClose={onClose}
      historyKey="match-review"
      className="match-modal merge-pair-dialog"
      // The decision is the footer's, pinned under a card tall enough to
      // scroll; moving through the queue sits at the start, where Delete sits
      // in a settings dialog.
      footer={
        <div className="dialog-actions">
          {error && <span className="dialog-form__error">{error}</span>}
          {pending.length > 1 && (
            <>
              <button
                type="button"
                className="dialog-btn dialog-btn--secondary match-modal__nav-btn"
                onClick={() => {
                  setError(null)
                  setIdx((i) => Math.max(0, i - 1))
                }}
                disabled={idx === 0}
                aria-label="Previous match"
              >
                <ChevronLeft size={13} aria-hidden="true" />
              </button>
              <button
                type="button"
                className="dialog-btn dialog-btn--secondary match-modal__nav-btn"
                onClick={() => {
                  setError(null)
                  setIdx((i) => Math.min(pending.length - 1, i + 1))
                }}
                disabled={idx === pending.length - 1}
                aria-label="Next match"
              >
                <ChevronRight size={13} aria-hidden="true" />
              </button>
            </>
          )}
          <div className="dialog-actions__end">
            {/* A queue of false alarms had no way out but this dialog, one
                pair at a time. */}
            {onKeepAllSeparate && pending.length > 1 && (
              <button
                type="button"
                className="dialog-btn dialog-btn--secondary"
                onClick={onKeepAllSeparate}
                disabled={deciding}
                title="None of these are duplicates — keep every pair as two transactions"
              >
                Keep all {pending.length} separate
              </button>
            )}
            <button
              type="button"
              className="dialog-btn dialog-btn--secondary"
              onClick={() => void decide(false)}
              disabled={deciding}
            >
              Keep separate
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--primary"
              onClick={() => void decide(true)}
              // Until the server has said what accepting leaves — or when it
              // has said these cannot be merged — there is nothing to accept.
              disabled={deciding || !ready}
            >
              Accept link
            </button>
          </div>
        </div>
      }
    >
      <MatchCard
        key={current.id}
        match={current}
        budgetId={budgetId}
        keep={keep}
        onKeepChange={(next) => setPicks({ matchId: current.id, keep: next })}
        onReady={setReady}
      />
    </Dialog>
  )
}
