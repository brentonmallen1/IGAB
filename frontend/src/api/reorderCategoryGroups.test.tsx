/**
 * Reordering category groups.
 *
 * The order is how a user reads their own budget, so two things matter: the
 * whole order goes up in ONE request (a half-applied drag leaves an order
 * nobody chose), and the grid shows the new order immediately — a drag that
 * snaps back for a round trip reads as a drag that failed.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const apiPost = vi.hoisted(() => vi.fn())
const toastError = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { post: apiPost },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))
vi.mock('react-hot-toast', () => ({ default: { error: toastError, success: vi.fn() } }))

import { useReorderCategoryGroups } from './categories'
import type { CategoryGroup } from '../types'

function group(id: string, name: string, sort_order: number): CategoryGroup {
  return { id, budget_id: 'b1', name, sort_order, is_hidden: false, is_system: false }
}

const GROUPS = [group('g1', 'Bills', 0), group('g2', 'Wants', 1), group('g3', 'Savings', 2)]

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useReorderCategoryGroups', () => {
  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    qc.setQueryData(['categoryGroups', 'b1'], GROUPS)
    apiPost.mockReset()
    apiPost.mockResolvedValue({ data: null })
    toastError.mockClear()
  })

  it('sends the whole order as one request', async () => {
    const { result } = renderHook(() => useReorderCategoryGroups('b1'), { wrapper })
    result.current.mutate(['g3', 'g1', 'g2'])

    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    expect(apiPost).toHaveBeenCalledWith('/b1/category-groups/reorder', {
      group_ids: ['g3', 'g1', 'g2'],
    })
  })

  it('shows the new order before the server answers', async () => {
    // Deliberately never resolves: the assertion is about what the grid does
    // while the request is still in flight.
    apiPost.mockImplementation(() => new Promise(() => {}))
    const { result } = renderHook(() => useReorderCategoryGroups('b1'), { wrapper })
    result.current.mutate(['g3', 'g1', 'g2'])

    await waitFor(() => {
      const cached = qc.getQueryData<CategoryGroup[]>(['categoryGroups', 'b1'])
      expect(cached?.map((g) => g.name)).toEqual(['Savings', 'Bills', 'Wants'])
    })
    // sort_order is renumbered too, so anything reading it agrees with the
    // order it is rendered in.
    expect(qc.getQueryData<CategoryGroup[]>(['categoryGroups', 'b1'])?.map((g) => g.sort_order))
      .toEqual([0, 1, 2])
  })

  it('puts the old order back when the server refuses', async () => {
    apiPost.mockRejectedValue(new Error('stale'))
    const { result } = renderHook(() => useReorderCategoryGroups('b1'), { wrapper })
    result.current.mutate(['g3', 'g1', 'g2'])

    await waitFor(() => expect(toastError).toHaveBeenCalled())
    const cached = qc.getQueryData<CategoryGroup[]>(['categoryGroups', 'b1'])
    expect(cached?.map((g) => g.name)).toEqual(['Bills', 'Wants', 'Savings'])
  })
})
