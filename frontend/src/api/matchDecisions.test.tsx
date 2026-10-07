/**
 * Settling a possible duplicate refreshes the reconcile status.
 *
 * An open pair holds a reconciliation back (`in_review_count`), and both
 * answers close it. Accept kept its own hand-written copy of the
 * transaction-change list, which had missed `reconcile-status`; it now runs
 * the shared one. Reject moves no money, so it names the one key it moves.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPost = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { post: apiPost, get: vi.fn().mockResolvedValue({ data: [] }) },
}))

import { useAcceptMatch, useRejectMatch } from './simplefin'
import { ROOT } from './queryKeys'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  apiPost.mockReset()
  apiPost.mockResolvedValue({ data: null })
})

function invalidatedRoots(spy: { mock: { calls: unknown[][] } }): unknown[] {
  return spy.mock.calls.map((c) => (c[0] as { queryKey: unknown[] }).queryKey[0])
}

describe('a match decision', () => {
  it('accepting refreshes the reconcile status and the budget it merged in', async () => {
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useAcceptMatch('b1'), { wrapper })
    result.current.mutate('m1')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const roots = invalidatedRoots(spy)
    expect(roots).toContain(ROOT.reconcileStatus)
    expect(roots).toContain(ROOT.simplefinMatches)
    expect(roots).toContain(ROOT.pendingMatchesAccount)
    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.accounts, 'b1'] })
  })

  it('rejecting refreshes the reconcile status', async () => {
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useRejectMatch(), { wrapper })
    result.current.mutate('m1')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(invalidatedRoots(spy)).toContain(ROOT.reconcileStatus)
  })
})
