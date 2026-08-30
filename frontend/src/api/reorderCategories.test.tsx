/**
 * Reordering the categories inside one group — the same contract as groups:
 * one request, shown before the server answers, restored if it refuses, and
 * never touching another group's rows.
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

import { useReorderCategories } from './categories'
import type { Category } from '../types'
import { makeCategory } from '../test-utils/factories'

function cat(id: string, name: string, group: string, sort_order: number): Category {
  return makeCategory({ id, name, category_group_id: group, sort_order })
}

// The server lists categories by position within the flat list; two groups
// interleave exactly as the grid receives them.
const LIST = [
  cat('c1', 'Rent', 'bills', 0),
  cat('w1', 'Games', 'wants', 0),
  cat('c2', 'Power', 'bills', 1),
  cat('c3', 'Water', 'bills', 2),
  cat('w2', 'Dining', 'wants', 1),
]
const KEY = ['categories', 'b1', false]

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}
const names = () => qc.getQueryData<Category[]>(KEY)?.map((c) => c.name)

describe('useReorderCategories', () => {
  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    qc.setQueryData(KEY, LIST)
    apiPost.mockReset()
    apiPost.mockResolvedValue({ data: null })
    toastError.mockClear()
  })

  it('sends the group and its whole order as one request', async () => {
    const { result } = renderHook(() => useReorderCategories('b1'), { wrapper })
    result.current.mutate({ groupId: 'bills', categoryIds: ['c3', 'c1', 'c2'] })

    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    expect(apiPost).toHaveBeenCalledWith('/b1/category-groups/bills/categories/reorder', {
      category_ids: ['c3', 'c1', 'c2'],
    })
  })

  it("shows the new order before the server answers and leaves other groups' rows alone", async () => {
    apiPost.mockImplementation(() => new Promise(() => {}))
    const { result } = renderHook(() => useReorderCategories('b1'), { wrapper })
    result.current.mutate({ groupId: 'bills', categoryIds: ['c3', 'c1', 'c2'] })

    await waitFor(() => expect(names()).toEqual(['Water', 'Games', 'Rent', 'Power', 'Dining']))
    const bills = qc.getQueryData<Category[]>(KEY)!.filter((c) => c.category_group_id === 'bills')
    expect(bills.map((c) => c.sort_order)).toEqual([0, 1, 2])
    const wants = qc.getQueryData<Category[]>(KEY)!.filter((c) => c.category_group_id === 'wants')
    expect(wants.map((c) => [c.name, c.sort_order])).toEqual([
      ['Games', 0],
      ['Dining', 1],
    ])
  })

  it('puts the old order back when the server refuses', async () => {
    apiPost.mockRejectedValue(new Error('stale'))
    const { result } = renderHook(() => useReorderCategories('b1'), { wrapper })
    result.current.mutate({ groupId: 'bills', categoryIds: ['c3', 'c1', 'c2'] })

    await waitFor(() => expect(toastError).toHaveBeenCalled())
    expect(names()).toEqual(['Rent', 'Games', 'Power', 'Water', 'Dining'])
  })
})
