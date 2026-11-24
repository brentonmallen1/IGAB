/**
 * Finishing a reconciliation refreshes the review counts.
 *
 * Finish locks the cleared rows and approves the ones still awaiting
 * approval. It kept a three-key invalidation list of its own that knew
 * nothing of the review counts, so the sidebar badge went on counting rows
 * the reconcile had just approved. Both reconcile writes run the shared
 * transaction-change list now.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPost = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { post: apiPost, get: vi.fn().mockResolvedValue({ data: [] }) },
}))

import { useCreateAdjustment, useFinishReconciliation } from './reconciliation'
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

describe('a reconcile write', () => {
  it('finishing refreshes the review counts for the rows it approved', async () => {
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useFinishReconciliation('b1', 'a1'), { wrapper })
    result.current.mutate({ statement_balance: 120 })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.pendingReviewCount] })
    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.pendingReviewCountAccount, 'a1'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.reconcileStatus] })
    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.accounts, 'b1'] })
  })

  it('an adjustment is a new transaction, and refreshes what one does', async () => {
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useCreateAdjustment('b1', 'a1'), { wrapper })
    result.current.mutate(-3.5)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.budgetMonth, 'b1'] })
    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.reconcileStatus] })
  })
})
