/**
 * The reports that end "today" send the browser's date.
 *
 * The server's clock is UTC, so every evening west of it the server is
 * already living tomorrow: the burn windows slid a day, and Cash Projection
 * started its path a day late with a history ending on a day the reader had
 * not finished. A hook that quietly stops sending `client_today` fails here.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { useBurnRateReport, useCashProjectionReport, useDashboardMetrics } from './reports'

vi.mock('./client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client')>()),
  apiClient: { get: vi.fn() },
}))

const ISO = /^\d{4}-\d{2}-\d{2}$/

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.mocked(apiClient.get).mockReset()
  vi.mocked(apiClient.get).mockResolvedValue({ data: {} } as never)
})

async function paramsOf(hook: () => unknown): Promise<Record<string, unknown>> {
  renderHook(hook, { wrapper })
  await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
  const { params } = vi.mocked(apiClient.get).mock.calls[0][1] as {
    params: Record<string, unknown> | URLSearchParams
  }
  // Some hooks build URLSearchParams to drop unset filters; read both alike.
  return params instanceof URLSearchParams ? Object.fromEntries(params) : params
}

describe('reports that end today name the day', () => {
  it('Cash Projection starts on the browser’s today', async () => {
    const params = await paramsOf(() => useCashProjectionReport('b1', 60))
    expect(params).toEqual({ days: 60, client_today: expect.stringMatching(ISO) })
  })

  it('the burn chart ends on it', async () => {
    const params = await paramsOf(() => useBurnRateReport('b1', 6))
    expect(params).toMatchObject({ months: 6, client_today: expect.stringMatching(ISO) })
  })

  it('the Overview’s metrics end on it', async () => {
    const params = await paramsOf(() => useDashboardMetrics('b1'))
    expect(params).toMatchObject({ client_today: expect.stringMatching(ISO) })
  })
})
