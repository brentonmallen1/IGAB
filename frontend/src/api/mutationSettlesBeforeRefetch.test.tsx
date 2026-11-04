/**
 * A write's `mutateAsync` resolves when the SERVER answers, not when every
 * query it invalidated has refetched.
 *
 * Editing a transaction invalidates eighteen query groups, and the editor
 * closes on `await updateTxn.mutateAsync(...)`. While `onSuccess` returned
 * the invalidation's promise, TanStack Query held the mutation pending until
 * the slowest refetch came back, so the editor sat open for all of them.
 * The rule is enforced by eslint (`NO_AWAITED_INVALIDATION`); these pin the
 * behaviour on the two writes the report was about — a transaction edit and
 * an assignment move — with a refetch that never finishes.
 */
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPatch = vi.hoisted(() => vi.fn())
const apiPost = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { patch: apiPatch, post: apiPost, get: vi.fn() },
}))

import { useMoveMoney } from './budgets'
import { ROOT } from './queryKeys'
import { useUpdateTransaction } from './transactions'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

/** An active query on `key`: its first fetch answers, every refetch hangs. */
const monthFetch = vi.fn<() => Promise<string>>()
function useHangingQuery(key: unknown[]) {
  return useQuery({ queryKey: key, queryFn: monthFetch })
}

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  apiPatch.mockReset()
  apiPost.mockReset()
  monthFetch.mockReset()
  monthFetch.mockResolvedValueOnce('first').mockReturnValue(new Promise<string>(() => {}))
})

describe('a write settles on the server’s answer', () => {
  it('updating a transaction resolves while the month is still refetching', async () => {
    apiPatch.mockResolvedValue({ data: { id: 't1', account_id: 'a1', changed: true } })
    const month = [ROOT.budgetMonth, 'b1', '2026-11-01']
    const { result } = renderHook(
      () => ({ month: useHangingQuery(month), update: useUpdateTransaction('b1') }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.month.data).toBe('first'))

    await expect(result.current.update.mutateAsync({ id: 't1', memo: 'x' })).resolves.toMatchObject(
      { id: 't1' }
    )
    // The refetch was asked for, and is still out.
    expect(qc.getQueryState(month)?.fetchStatus).toBe('fetching')
  })

  it('moving money resolves while the month is still refetching', async () => {
    apiPost.mockResolvedValue({ data: null })
    const month = [ROOT.budgetMonth, 'b1', '2026-11-01']
    const { result } = renderHook(
      () => ({ month: useHangingQuery(month), move: useMoveMoney('b1') }),
      { wrapper }
    )
    await waitFor(() => expect(result.current.month.data).toBe('first'))

    await result.current.move.mutateAsync({
      from_category_id: null,
      to_category_id: 'c1',
      amount: 5,
      month: '2026-11-01',
    })
    expect(qc.getQueryState(month)?.fetchStatus).toBe('fetching')
  })
})
