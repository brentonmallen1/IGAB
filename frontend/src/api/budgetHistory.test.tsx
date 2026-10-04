/**
 * The history switch and the import's history choice reach the server as
 * the person chose them — and the switch sweeps every figure the mode moves.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiPost = vi.hoisted(() => vi.fn())
const apiPut = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { post: apiPost, put: apiPut, get: vi.fn().mockResolvedValue({ data: [] }) },
}))

import { useImportYnabAsBudget, useSetBudgetHistory } from './budgets'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  apiPost.mockReset()
  apiPut.mockReset()
})

describe('the import’s history choice', () => {
  const file = new File(['x'], 'export.zip')
  const imported = { data: { budget: { id: 'b1' }, import_result: {} } }

  it('sends the chosen mode', async () => {
    apiPost.mockResolvedValue(imported)
    const { result } = renderHook(() => useImportYnabAsBudget(), { wrapper })
    result.current.mutate({ name: 'Home', file, historyMode: 'rederived' })
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    const form = apiPost.mock.calls[0][1] as FormData
    expect(form.get('history_mode')).toBe('rederived')
  })

  it('sends none when the export offered no choice', async () => {
    apiPost.mockResolvedValue(imported)
    const { result } = renderHook(() => useImportYnabAsBudget(), { wrapper })
    result.current.mutate({ name: 'Home', file })
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect((apiPost.mock.calls[0][1] as FormData).has('history_mode')).toBe(false)
  })
})

describe('the history switch', () => {
  it('puts the mode and refreshes the month it moved', async () => {
    apiPut.mockResolvedValue({ data: { mode: 'rederived', import_month: '2026-10-01' } })
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useSetBudgetHistory('b1'), { wrapper })
    result.current.mutate('rederived')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiPut).toHaveBeenCalledWith('/budgets/b1/history', { mode: 'rederived' })
    const roots = spy.mock.calls.map((c) => (c[0]!.queryKey as unknown[])[0])
    expect(roots).toContain('budgetMonth')
    expect(qc.getQueryData(['budget-history', 'b1'])).toEqual({
      mode: 'rederived',
      import_month: '2026-10-01',
    })
  })
})
