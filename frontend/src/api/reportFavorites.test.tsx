/**
 * The server stores the starred list and never reads it
 * (`services/report_favorites.py`), so ids of reports since merged are still
 * in it. Breakdown, Pareto and Treemap became Where it went; Budget vs Actual,
 * Cumulative Variance and Plan vs Reality became Plan vs Spent. A star on any
 * of them must star the new report — once — rather than vanish or draw a tab
 * that no longer renders (`RETIRED_REPORT_TABS`).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
const apiPut = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({
  apiClient: { get: apiGet, put: apiPut },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

import { useReportFavorites, useSetReportFavorites } from './reportFavorites'
import { toggleFavorite } from '../pages/ReportsPage/reportNav'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('useReportFavorites', () => {
  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    apiGet.mockReset()
    apiPut.mockReset()
  })

  it('stars the successor of a merged report, once, where the old star sat', async () => {
    apiGet.mockResolvedValue({
      data: { tabs: ['essentials', 'pareto', 'net-worth', 'treemap', 'spending-breakdown'] },
    })
    const { result } = renderHook(() => useReportFavorites('b1'), { wrapper })
    await waitFor(() =>
      expect(result.current.data).toEqual(['essentials', 'where-it-went', 'net-worth'])
    )
  })

  it('reads a star on a plan-family report as a star on Plan vs Spent', async () => {
    apiGet.mockResolvedValue({
      data: { tabs: ['budget-actual', 'savings', 'variance', 'plan-reality', 'debts'] },
    })
    const { result } = renderHook(() => useReportFavorites('b1'), { wrapper })
    // Three stars on the one report are one, where the first stood; an id no
    // build maps still drops.
    await waitFor(() => expect(result.current.data).toEqual(['plan-vs-spent', 'savings']))
  })

  it('maps both merges in one starred row', async () => {
    apiGet.mockResolvedValue({
      data: { tabs: ['treemap', 'variance', 'pareto', 'budget-actual', 'essentials'] },
    })
    const { result } = renderHook(() => useReportFavorites('b1'), { wrapper })
    await waitFor(() =>
      expect(result.current.data).toEqual(['where-it-went', 'plan-vs-spent', 'essentials'])
    )
  })

  it('still drops an id that names nothing', async () => {
    apiGet.mockResolvedValue({ data: { tabs: ['debts', 'seasonality', 'constructor'] } })
    const { result } = renderHook(() => useReportFavorites('b1'), { wrapper })
    await waitFor(() => expect(result.current.data).toEqual(['seasonality']))
  })

  it('writes the live ids back the next time a star is toggled', async () => {
    // The row the client read is what it sends, so the stored list sheds the
    // old ids without a migration on the server.
    apiGet.mockResolvedValue({ data: { tabs: ['pareto', 'essentials', 'plan-reality'] } })
    apiPut.mockImplementation(async (_url: string, body: { tabs: string[] }) => ({ data: body }))
    const read = renderHook(() => useReportFavorites('b1'), { wrapper })
    await waitFor(() => expect(read.result.current.data).toBeDefined())
    const write = renderHook(() => useSetReportFavorites('b1'), { wrapper })

    await write.result.current.mutateAsync(toggleFavorite(read.result.current.data!, 'net-worth'))

    expect(apiPut).toHaveBeenCalledWith('/b1/reports/favorites', {
      tabs: ['where-it-went', 'essentials', 'plan-vs-spent', 'net-worth'],
    })
  })
})
