/**
 * Starred reports are a list the server stores and never interprets, so a
 * star on a report that has since been merged into another arrives as the old
 * id. It must come back as the report that replaced it (`retiredReportTabs`),
 * not vanish from the starred row.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { useReportFavorites } from './reportFavorites'

vi.mock('./client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client')>()),
  apiClient: { get: vi.fn(), put: vi.fn() },
}))

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset()
})

describe('useReportFavorites', () => {
  it('reads a star on a merged report as a star on the report that replaced it', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { tabs: ['budget-actual', 'savings', 'variance', 'plan-reality', 'debts'] },
    } as never)
    const { result } = renderHook(() => useReportFavorites('b1'), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())
    // Three stars on the one report are one, where the first stood; an id no
    // build maps still drops.
    expect(result.current.data).toEqual(['plan-vs-spent', 'savings'])
  })
})
