/**
 * The wishlist sends the browser's date, on every call that needs one.
 *
 * The server cannot work it out — it does not know the caller's timezone, so
 * its own clock is already tomorrow every evening west of UTC. An ending
 * stamped with that date lands in the wrong bucket in the discipline report
 * ("cooled off, then dropped" is decided by comparing it with
 * `cooling_until`), and cooling-off itself reads a day early.
 *
 * This is the ratchet: the fix lives in one place per call, and a call that
 * quietly stops sending it fails here rather than months later in a report.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { apiClient } from './client'
import { useDeleteWish, useSettleWish, useUpdateWish, useWishlist } from './wishlist'

vi.mock('./client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client')>()),
  apiClient: { get: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

const ISO = /^\d{4}-\d{2}-\d{2}$/

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.mocked(apiClient.get).mockResolvedValue({ data: {} } as never)
  vi.mocked(apiClient.patch).mockResolvedValue({ data: {} } as never)
  vi.mocked(apiClient.post).mockResolvedValue({ data: {} } as never)
  vi.mocked(apiClient.delete).mockResolvedValue({ data: {} } as never)
})

describe('the wishlist client names the day', () => {
  it('reads the list for the browser’s today', async () => {
    renderHook(() => useWishlist('b1'), { wrapper })
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled())
    expect(vi.mocked(apiClient.get).mock.calls[0][1]).toMatchObject({
      params: { today: expect.stringMatching(ISO) },
    })
  })

  it('stamps an ending with it', async () => {
    const { result } = renderHook(() => useUpdateWish('b1'), { wrapper })
    result.current.mutate({ id: 'w1', status: 'dropped' })
    await waitFor(() => expect(apiClient.patch).toHaveBeenCalled())
    expect(vi.mocked(apiClient.patch).mock.calls[0][1]).toMatchObject({
      status: 'dropped',
      client_today: expect.stringMatching(ISO),
    })
  })

  it('lets a caller override it rather than silently winning', async () => {
    const { result } = renderHook(() => useUpdateWish('b1'), { wrapper })
    result.current.mutate({ id: 'w1', status: 'done', client_today: '2020-01-01' })
    await waitFor(() => expect(apiClient.patch).toHaveBeenCalled())
    expect(vi.mocked(apiClient.patch).mock.calls[0][1]).toMatchObject({
      client_today: '2020-01-01',
    })
  })

  it('quotes the envelope balance for the right month on delete', async () => {
    const { result } = renderHook(() => useDeleteWish('b1'), { wrapper })
    result.current.mutate('w1')
    await waitFor(() => expect(apiClient.delete).toHaveBeenCalled())
    expect(vi.mocked(apiClient.delete).mock.calls[0][1]).toMatchObject({
      params: { today: expect.stringMatching(ISO) },
    })
  })

  it('settles in the month the person is looking at', async () => {
    const { result } = renderHook(() => useSettleWish('b1'), { wrapper })
    result.current.mutate({ id: 'w1', destination_category_id: null, keep_envelope: false })
    await waitFor(() => expect(apiClient.post).toHaveBeenCalled())
    expect(vi.mocked(apiClient.post).mock.calls[0][1]).toMatchObject({
      client_today: expect.stringMatching(ISO),
    })
  })
})
