/**
 * The inspector's history is the viewed month's, and its buttons draw their
 * result at once — then take it back if the server refuses.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth } from '../types'
import { makeCategoryBalance } from '../test-utils/factories'

const apiPost = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({ apiClient: { post: apiPost, get: vi.fn() } }))

import { useAutoAssign, useCategoryHistoryBatch } from './categoryHistory'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  apiPost.mockReset()
})

describe('useCategoryHistoryBatch', () => {
  it('asks for the viewed month, and keeps each month apart', async () => {
    apiPost.mockResolvedValue({ data: [] })
    const { rerender } = renderHook(({ month }) => useCategoryHistoryBatch('b1', ['c1'], month), {
      wrapper,
      initialProps: { month: '2026-06-01' },
    })
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    expect(apiPost.mock.calls[0]).toEqual([
      '/b1/categories/history/batch',
      { category_ids: ['c1'] },
      { params: { month: '2026-06-01' } },
    ])

    // Another month is another question: a fresh request, not June's answer.
    rerender({ month: '2026-07-01' })
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2))
    expect(apiPost.mock.calls[1][2]).toEqual({ params: { month: '2026-07-01' } })
  })
})

describe('useAutoAssign', () => {
  const key = ['budgetMonth', 'b1', '2026-07-01']
  const july = {
    month: '2026-07-01',
    to_be_assigned: 500,
    total_assigned: 100,
    category_balances: [makeCategoryBalance({ category_id: 'c1', assigned: 100, available: 100 })],
  } as unknown as BudgetMonth

  it('draws the new figures before the server answers', async () => {
    let answer: (v: unknown) => void = () => {}
    apiPost.mockReturnValue(new Promise((resolve) => (answer = resolve)))
    qc.setQueryData(key, july)
    const { result } = renderHook(() => useAutoAssign('b1', '2026-07-01'), { wrapper })

    result.current.mutate({
      categoryIds: ['c1'],
      action: 'last_month_assigned',
      amounts: new Map([['c1', 250]]),
    })

    await waitFor(() =>
      expect(qc.getQueryData<BudgetMonth>(key)?.category_balances[0].assigned).toBe(250)
    )
    expect(qc.getQueryData<BudgetMonth>(key)?.to_be_assigned).toBe(350)
    answer({ data: null })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
  })

  it('puts the month back when the server refuses', async () => {
    apiPost.mockRejectedValue(new Error('Income categories do not hold money'))
    qc.setQueryData(key, july)
    const { result } = renderHook(() => useAutoAssign('b1', '2026-07-01'), { wrapper })

    result.current.mutate({ categoryIds: ['c1'], action: 'reset', amounts: new Map([['c1', 0]]) })

    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(qc.getQueryData<BudgetMonth>(key)).toEqual(july)
  })

  it('draws nothing when the figures are not known yet', async () => {
    apiPost.mockResolvedValue({ data: null })
    qc.setQueryData(key, july)
    const { result } = renderHook(() => useAutoAssign('b1', '2026-07-01'), { wrapper })

    result.current.mutate({ categoryIds: ['c1'], action: 'average_spent', amounts: null })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiPost).toHaveBeenCalledWith('/b1/categories/auto-assign', {
      category_ids: ['c1'],
      action: 'average_spent',
      month: '2026-07-01',
    })
  })
})
