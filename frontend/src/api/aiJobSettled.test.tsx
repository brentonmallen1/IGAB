/**
 * A job that settles refreshes the register, whichever query watched it.
 *
 * Reprocessing a scan refreshed its row on the server and left the register
 * showing the old one: only the scan tab's own watcher invalidated anything,
 * and a reprocess starts from the AI page or the editor.
 */
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { AIJob, AIJobListResponse, AIJobStatus } from './aiJobs'
import {
  isJobInFlight,
  settledJobs,
  showJobQueued,
  useInvalidateWhenJobsSettle,
} from './aiJobSettled'
import { ROOT } from './queryKeys'

function job(status: AIJobStatus, over: Partial<AIJob> = {}): AIJob {
  return {
    id: 'j1',
    budget_id: 'b1',
    kind: 'receipt',
    status,
    payload: {},
    result: null,
    error: null,
    model: null,
    attempts: 1,
    max_attempts: 3,
    transaction_id: 't1',
    transaction_removed: false,
    needs_review: true,
    transaction_account_id: 'a1',
    transaction_category_id: null,
    transaction_is_split: false,
    card_ending_account_id: null,
    attachment_id: null,
    created_at: '2026-08-01T00:00:00Z',
    started_at: null,
    finished_at: null,
    ...over,
  }
}

describe('isJobInFlight', () => {
  it.each([
    ['queued', true],
    ['processing', true],
    ['done', false],
    ['error', false],
    // The single-job poll said "not done and not error", so a receipt that
    // settled as unplaced was polled every two seconds for as long as the
    // tab stayed open.
    ['unplaced', false],
  ] as const)('%s → %s', (status, inFlight) => {
    expect(isJobInFlight(status)).toBe(inFlight)
  })
})

describe('settledJobs', () => {
  const seen = (status: AIJobStatus) => new Map([['j1', status]])

  it.each(['done', 'error', 'unplaced'] as const)('in flight → %s is news', (status) => {
    expect(settledJobs(seen('processing'), [job(status)])).toHaveLength(1)
  })

  it('a job first seen settled is history, not news', () => {
    expect(settledJobs(new Map(), [job('done')])).toEqual([])
  })

  it('a job that stays settled is news once', () => {
    expect(settledJobs(seen('done'), [job('done')])).toEqual([])
  })

  it('a job still in flight is not news yet', () => {
    expect(settledJobs(seen('queued'), [job('processing')])).toEqual([])
  })
})

function harness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(qc, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const invalidated = () => invalidate.mock.calls.map(([filters]) => filters?.queryKey)
  return { qc, invalidate, wrapper, invalidated }
}

describe('useInvalidateWhenJobsSettle', () => {
  it('refreshes the register, the month and the accounts when a job settles', () => {
    const { wrapper, invalidated } = harness()
    const { rerender } = renderHook(({ jobs }) => useInvalidateWhenJobsSettle(jobs), {
      wrapper,
      initialProps: { jobs: [job('processing')] },
    })
    expect(invalidated()).toEqual([])

    rerender({ jobs: [job('done')] })

    expect(invalidated()).toEqual(
      expect.arrayContaining([
        [ROOT.transactions],
        [ROOT.budgetMonth, 'b1'],
        [ROOT.accounts, 'b1'],
        [ROOT.transaction, 't1'],
        [ROOT.aiJobForTxn],
      ])
    )
  })

  it('does nothing for jobs that were already settled when first seen', () => {
    const { wrapper, invalidate } = harness()
    const { rerender } = renderHook(({ jobs }) => useInvalidateWhenJobsSettle(jobs), {
      wrapper,
      initialProps: { jobs: [job('done')] },
    })
    rerender({ jobs: [job('done')] })
    expect(invalidate).not.toHaveBeenCalled()
  })

  it('invalidates once, not on every later render', () => {
    const { wrapper, invalidate } = harness()
    const { rerender } = renderHook(({ jobs }) => useInvalidateWhenJobsSettle(jobs), {
      wrapper,
      initialProps: { jobs: [job('queued')] },
    })
    rerender({ jobs: [job('done')] })
    const calls = invalidate.mock.calls.length
    rerender({ jobs: [job('done')] })
    expect(invalidate.mock.calls.length).toBe(calls)
  })
})

describe('showJobQueued', () => {
  it('puts the requeued job in every cache that shows it', () => {
    const { qc } = harness()
    const listKey = [ROOT.aiJobs, 'b1', { needsReview: true }]
    const other = job('done', { id: 'j2' })
    qc.setQueryData<AIJobListResponse>(listKey, {
      jobs: [job('done'), other],
      total_count: 2,
    })

    showJobQueued(qc, 'b1', job('queued'))

    expect(qc.getQueryData<AIJob>([ROOT.aiJob, 'b1', 'j1'])?.status).toBe('queued')
    expect(qc.getQueryData<AIJob>([ROOT.aiJobForTxn, 'b1', 't1'])?.status).toBe('queued')
    const list = qc.getQueryData<AIJobListResponse>(listKey)
    expect(list?.jobs.map((j) => j.status)).toEqual(['queued', 'done'])
    expect(list?.jobs[1]).toBe(other)
  })
})
