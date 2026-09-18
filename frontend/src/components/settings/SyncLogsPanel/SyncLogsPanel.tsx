import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight, Link2, RefreshCw } from 'lucide-react'

import toast from 'react-hot-toast'

import {
  useSyncRun,
  useSyncRuns,
  useUndoSyncRun,
  type SyncRun,
  type SyncRunAccount,
} from '../../../api/syncLogs'
import { confirmAsync } from '../../../stores/confirmStore'
import { useAppStore } from '../../../stores/appStore'
import { parseApiDecimal } from '../../../utils/money'
import { useFormatters } from '../../../hooks/useFormatters'
import {
  accountNote,
  describeSkipReason,
  describeWindow,
  runHeadline,
  runVerdict,
  windowDays,
} from './syncRunSummary'
import './SyncLogsPanel.css'

/**
 * What every bank sync actually did.
 *
 * Built after a re-linked account spent nine days syncing on schedule,
 * reporting success and importing none of its transactions. The app had no
 * memory of any run, so there was nothing to look at and nothing in
 * `docker logs` either.
 */
export function SyncLogsPanel() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data, isLoading } = useSyncRuns(budgetId, { limit: 50 })

  if (!budgetId) return null
  if (isLoading) return <div className="sync-logs__empty">Loading…</div>

  const runs = data?.runs ?? []
  if (runs.length === 0) {
    return (
      <div className="sync-logs__empty">
        No syncs recorded yet. Every sync from now on leaves a record here — what window was asked
        for, what each account returned, and why anything was skipped.
      </div>
    )
  }

  return (
    <div className="sync-logs">
      <p className="sync-logs__blurb">
        The last {runs.length} sync{runs.length === 1 ? '' : 's'}, newest first. Kept for 30 days.
      </p>
      <div className="sync-logs__list">
        {runs.map((run) => (
          <RunRow key={run.id} run={run} budgetId={budgetId} />
        ))}
      </div>
    </div>
  )
}

function RunRow({ run, budgetId }: { run: SyncRun; budgetId: string }) {
  const [open, setOpen] = useState(false)
  const verdict = runVerdict(run)
  const when = new Date(run.created_at)

  return (
    <div className={`sync-run sync-run--${verdict}`}>
      <button
        type="button"
        className="sync-run__head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span className={`sync-run__pill sync-run__pill--${verdict}`}>{verdict}</span>
        <span className="sync-run__when" title={when.toLocaleString()}>
          {when.toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
          })}
        </span>
        <span className="sync-run__headline">{runHeadline(run)}</span>
        {run.duration_ms != null && (
          <span className="sync-run__duration">{(run.duration_ms / 1000).toFixed(1)}s</span>
        )}
      </button>
      {open && <RunDetail runId={run.id} budgetId={budgetId} />}
    </div>
  )
}

function RunDetail({ runId, budgetId }: { runId: string; budgetId: string }) {
  const { data: run, isLoading } = useSyncRun(budgetId, runId)
  const undo = useUndoSyncRun(budgetId)
  if (isLoading || !run) return <div className="sync-run__detail">Loading…</div>

  const touched = run.imported + run.adopted + run.matched + run.cleared + run.removed_pending
  const canUndo = !!run.change_batch_id && !run.undone_at && touched > 0

  async function handleUndo() {
    if (!run) return
    const ok = await confirmAsync({
      title: 'Undo this sync?',
      message:
        `Takes back what this run did: ${run.imported} imported, ${run.adopted} re-linked, ` +
        `${run.matched} matched, ${run.removed_pending} removed. Rows you have edited since are ` +
        'left alone.',
      confirmLabel: 'Undo run',
      destructive: true,
    })
    if (!ok) return
    try {
      const result = await undo.mutateAsync(run.id)
      const parts = [`Undid ${result.undone} change${result.undone === 1 ? '' : 's'}`]
      if (result.skipped) parts.push(`${result.skipped} edited since were left alone`)
      toast.success(parts.join(' — '))
    } catch {
      toast.error('Could not undo this run')
    }
  }

  const days = windowDays(run)
  const skips = Object.entries(run.skip_reasons)

  return (
    <div className="sync-run__detail">
      {run.orphaned_links.map((orphan) => (
        <div key={orphan.stored_simplefin_id} className="sync-run__fault">
          <AlertTriangle size={13} />
          <div>
            <strong>{orphan.account_name}</strong> is linked to a bank account the feed no longer
            offers.{' '}
            {orphan.suggested_feed_name ? (
              <>
                It looks like <strong>{orphan.suggested_feed_name}</strong> is its replacement —
                relink it in that account&rsquo;s settings to resume importing.
              </>
            ) : orphan.may_need_auth ? (
              <>
                The bridge also reported an institution needing re-authentication, so this is more
                likely a lapsed login than a re-issued account: sign in again at the SimpleFIN
                bridge. Nothing was removed here.
              </>
            ) : (
              <>Relink it in that account&rsquo;s settings to resume importing.</>
            )}
          </div>
        </div>
      ))}

      {run.balance_drift.map((drift) => (
        <div key={drift.account_id} className="sync-run__fault">
          <AlertTriangle size={13} />
          <div>
            <strong>{drift.account_name}</strong> is off from what the bank reports — the ledger
            here does not add up to the bank&rsquo;s balance. Rows may have posted in days this sync
            never asked for: fetch the last 90 days again from that account&rsquo;s settings, then
            reconcile.
          </div>
        </div>
      ))}

      {run.bank_errors.map((err, i) => (
        <div key={`${err.code}-${i}`} className="sync-run__fault sync-run__fault--bank">
          <AlertTriangle size={13} />
          <div>
            <code>{err.code}</code> {err.message}
          </div>
        </div>
      ))}

      {run.undone_at && (
        <div className="sync-run__fault sync-run__fault--undone">
          <RefreshCw size={13} />
          <div>This run was undone {new Date(run.undone_at).toLocaleString()}.</div>
        </div>
      )}

      <dl className="sync-run__facts">
        <Fact label="Window asked for">
          {describeWindow(run) ?? '—'}
          {days != null && days > 90 && (
            <span className="sync-run__warn"> — over the bridge&rsquo;s 90-day limit</span>
          )}
        </Fact>
        <Fact label="Rows in feed">{run.feed_txn_count}</Fact>
        <Fact label="Imported">{run.imported}</Fact>
        {run.adopted > 0 && (
          <Fact label="Re-linked">
            {run.adopted}
            <span className="sync-run__hint"> existing rows took new bank ids</span>
          </Fact>
        )}
        <Fact label="Matched">{run.matched}</Fact>
        <Fact label="Cleared">{run.cleared}</Fact>
      </dl>

      {skips.length > 0 && (
        <div className="sync-run__skips">
          <h4>Skipped {run.skipped}</h4>
          <ul>
            {skips.map(([reason, count]) => (
              <li key={reason}>
                <strong>{count}</strong> {describeSkipReason(reason)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {canUndo && (
        <div className="sync-run__actions">
          <button
            type="button"
            className="dialog-btn dialog-btn--secondary"
            onClick={() => void handleUndo()}
            disabled={undo.isPending}
          >
            {undo.isPending ? 'Undoing…' : 'Undo this run'}
          </button>
          <span className="sync-run__hint">
            Takes back every row this run imported, re-linked or removed. Rows you edited since
            stay.
          </span>
        </div>
      )}

      {run.accounts.length > 0 && (
        <table className="sync-run__accounts">
          <thead>
            <tr>
              <th>Account</th>
              <th>Rows</th>
              <th>Oldest at bank</th>
              <th>Newest at bank</th>
              <th>Bank balance</th>
              <th>Ledger</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {run.accounts.map((account) => (
              <AccountRow key={account.account_id ?? account.simplefin_account_id} a={account} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function AccountRow({ a }: { a: SyncRunAccount }) {
  const note = accountNote(a)
  const { formatMoney } = useFormatters()
  const money = (v: string | null) => (v == null ? '—' : formatMoney(parseApiDecimal(v)))
  const off =
    a.bank_balance != null &&
    a.ledger_cleared_balance != null &&
    parseApiDecimal(a.bank_balance) !== parseApiDecimal(a.ledger_cleared_balance)
  return (
    <tr className={a.orphaned ? 'sync-run__account--orphaned' : undefined}>
      <td>{a.account_name ?? a.simplefin_account_id}</td>
      <td>{a.feed_txn_count}</td>
      <td>{a.feed_oldest_date ?? '—'}</td>
      <td>{a.feed_newest_date ?? '—'}</td>
      <td className="tabular">{money(a.bank_balance)}</td>
      <td className={`tabular${off ? ' sync-run__off' : ''}`}>{money(a.ledger_cleared_balance)}</td>
      <td className="sync-run__note">
        {note && (
          <>
            {a.orphaned ? <Link2 size={11} /> : <RefreshCw size={11} />} {note}
          </>
        )}
      </td>
    </tr>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="sync-run__fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}
