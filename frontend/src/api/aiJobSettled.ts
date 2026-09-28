import { useEffect, useRef } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import type { AIJob, AIJobListResponse, AIJobStatus } from './aiJobs'
import { invalidateAfterTransactionChange } from './invalidateAfterTransactionChange'
import { ROOT } from './queryKeys'

/**
 * A job that finishes has written a transaction outside any mutation hook.
 *
 * The worker creates the row, refreshes it on a reprocess, or puts the
 * receipt on the bank's row — and no mutation on this side saw any of it.
 * So whichever query watches a job notices it leave the queue and stales
 * what a transaction change stales. Before this, only the scan tab's own
 * watcher did; a reprocess started from the AI page or the editor refreshed
 * the row on the server and left the register showing the old one until a
 * reload.
 *
 * "In flight" was spelled three ways: the list poll said queued or
 * processing, the single-job poll said "not done and not error" (so an
 * `unplaced` receipt polled every two seconds forever), and the scan tab said
 * "done or error". It is spelled once, here.
 */

/** Still waiting for the worker. Everything else is settled. */
export function isJobInFlight(status: AIJobStatus): boolean {
  return status === 'queued' || status === 'processing'
}

/** The jobs in `after` last seen in flight that are not any more. A job
 *  never seen before is not news: a list's first load is history. */
export function settledJobs(
  before: ReadonlyMap<string, AIJobStatus>,
  after: readonly AIJob[]
): AIJob[] {
  return after.filter((job) => {
    const was = before.get(job.id)
    return was !== undefined && isJobInFlight(was) && !isJobInFlight(job.status)
  })
}

/** Everything a settled job can have made stale. */
export function invalidateAfterJobSettled(qc: QueryClient, job: AIJob): Promise<void> {
  return Promise.all([
    invalidateAfterTransactionChange(qc, {
      budgetId: job.budget_id,
      accountId: job.transaction_account_id,
      transactionIds: job.transaction_id ? [job.transaction_id] : [],
    }),
    qc.invalidateQueries({ queryKey: [ROOT.aiJobForTxn] }),
  ]).then(() => undefined)
}

/** Put a job the server just queued again into every cache that shows it,
 *  so its watchers see it in flight before it settles. Without this a fast
 *  worker can finish before the next poll, and the watcher only ever sees
 *  "done" then "done" — never the move it is waiting for. */
export function showJobQueued(qc: QueryClient, budgetId: string, job: AIJob): void {
  qc.setQueryData([ROOT.aiJob, budgetId, job.id], job)
  if (job.transaction_id) qc.setQueryData([ROOT.aiJobForTxn, budgetId, job.transaction_id], job)
  qc.setQueriesData<AIJobListResponse>({ queryKey: [ROOT.aiJobs, budgetId] }, (old) =>
    old?.jobs ? { ...old, jobs: old.jobs.map((j) => (j.id === job.id ? job : j)) } : old
  )
}

/** Watch `jobs` (a query's current data) and invalidate once for each that
 *  settles. Pass a stable array: it is an effect dependency. */
export function useInvalidateWhenJobsSettle(jobs: readonly AIJob[]): void {
  const qc = useQueryClient()
  const seen = useRef(new Map<string, AIJobStatus>())
  useEffect(() => {
    for (const job of settledJobs(seen.current, jobs)) void invalidateAfterJobSettled(qc, job)
    for (const job of jobs) seen.current.set(job.id, job.status)
  }, [jobs, qc])
}
