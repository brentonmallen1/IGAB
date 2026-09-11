/**
 * The volatility query carries its amortize flag in both the key and the
 * request. Without it in the key, React Query serves the cached raw reading
 * while the box is ticked; without it in the params, the server computes the
 * raw one. Either way the chart lies quietly beside a panel describing the
 * amortized figures.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { get: apiGet },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import { useVolatilityReport } from './reports'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useVolatilityReport', () => {
  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    apiGet.mockReset()
    apiGet.mockImplementation(async (_url: string, cfg: { params: { amortize: boolean } }) => ({
      data: { categories: [], amortized: cfg.params.amortize },
    }))
  })

  it('refetches with the flag when amortize flips, rather than serving the raw reading', async () => {
    const { result, rerender } = renderHook(
      ({ amortize }) => useVolatilityReport('b1', 6, amortize),
      { wrapper, initialProps: { amortize: false } }
    )
    await waitFor(() => expect(result.current.data?.amortized).toBe(false))

    rerender({ amortize: true })

    await waitFor(() => expect(result.current.data?.amortized).toBe(true))
    expect(apiGet).toHaveBeenCalledTimes(2)
    expect(apiGet).toHaveBeenLastCalledWith('/b1/reports/volatility', {
      params: { months: 6, amortize: true },
    })
  })

  it('keeps the two readings under different keys', async () => {
    renderHook(() => useVolatilityReport('b1', 6, false), { wrapper })
    renderHook(() => useVolatilityReport('b1', 6, true), { wrapper })
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
    const keys = qc
      .getQueryCache()
      .findAll({ queryKey: ['reports', 'volatility'] })
      .map((q) => q.queryKey)
    expect(keys).toHaveLength(2)
  })
})
