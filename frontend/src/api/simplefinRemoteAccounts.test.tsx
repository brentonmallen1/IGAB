/**
 * Listing the bank's accounts spends a request from the day's all-accounts
 * quota. The app-wide default retries a failed query once, which for a 429
 * asks again for something just refused — and spends nothing but patience.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('./client', () => ({ apiClient: { get: apiGet } }))

import { useSimpleFINRemoteAccounts } from './simplefin'
import { ROOT } from './queryKeys'

let qc: QueryClient
function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  // The app's own default (App.tsx): one retry.
  qc = new QueryClient({ defaultOptions: { queries: { retry: 1, retryDelay: 0 } } })
  apiGet.mockReset()
})

describe('useSimpleFINRemoteAccounts', () => {
  it('asks once when the quota is spent, and keeps the server’s reason', async () => {
    const refused = {
      response: {
        status: 429,
        data: { detail: 'Daily global sync limit of 12 requests reached.' },
      },
    }
    apiGet.mockRejectedValue(refused)
    const { result } = renderHook(() => useSimpleFINRemoteAccounts('conn-1'), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBe(refused)
  })

  it('moves the quota bars after asking, answered or not', async () => {
    apiGet.mockResolvedValue({ data: [{ id: 'ACT-sapphire', name: 'Sapphire Visa' }] })
    const spy = vi.spyOn(qc, 'invalidateQueries')
    const { result } = renderHook(() => useSimpleFINRemoteAccounts('conn-1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalledWith({ queryKey: [ROOT.simplefinRateLimit] })
  })
})
