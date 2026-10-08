/**
 * The quota bars draw the limits the server serves. The panel used to write
 * "/ 12" itself — a second copy of a number the service enforces, free to
 * disagree with it the day either changes.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SimpleFINPanel } from './SimpleFINPanel'
import type { SimpleFINRateLimitStatus } from '../../../types'

const status = vi.hoisted(() => ({
  current: undefined as SimpleFINRateLimitStatus | undefined,
}))

vi.mock('../../../api/simplefin', () => {
  const idle = () => ({ mutate: vi.fn(), isPending: false })
  return {
    useSimpleFINConnections: () => ({
      data: [
        {
          id: 'conn-1',
          last_sync_at: null,
          sync_enabled: true,
          sync_hours: [],
          last_sync_error: null,
          last_sync_error_at: null,
        },
      ],
    }),
    useSimpleFINRateLimitStatus: () => ({ data: status.current }),
    useUpdateSimpleFINConnection: idle,
    useDeleteSimpleFINConnection: idle,
  }
})
vi.mock('../../../api/settings', () => ({
  useSettings: () => ({ data: [] }),
  useUpdateSetting: () => ({ mutate: vi.fn() }),
}))
vi.mock('../../../hooks/useFormatters', () => ({
  useFormatters: () => ({ formatDateTime: (d: string) => d }),
}))
vi.mock('../../simplefin/SimpleFINSetup', () => ({
  SimpleFINSetup: () => null,
  SimpleFINConfigNotice: () => null,
}))
vi.mock('../SyncSchedule/SyncSchedule', () => ({ SyncSchedule: () => null }))

function served(over: Partial<SimpleFINRateLimitStatus>): SimpleFINRateLimitStatus {
  return {
    global_used: 0,
    global_remaining: 0,
    global_limit: 0,
    account_used: 0,
    account_remaining: 0,
    account_limit: 0,
    can_sync_global: true,
    can_sync_account: true,
    resets_at: '2026-10-08T00:00:00+00:00',
    ...over,
  }
}

describe('SimpleFINPanel quota', () => {
  it('reads each limit from the status response', () => {
    // Deliberately not 12: a hard-coded copy would still draw "/ 12".
    status.current = served({
      global_used: 3,
      global_limit: 10,
      account_used: 2,
      account_limit: 14,
    })
    render(<SimpleFINPanel />)
    expect(screen.getByText('3 / 10')).toBeInTheDocument()
    expect(screen.getByText('2 / 14')).toBeInTheDocument()
  })

  it('fills each bar against its own limit', () => {
    status.current = served({
      global_used: 5,
      global_limit: 10,
      account_used: 7,
      account_limit: 14,
    })
    const { container } = render(<SimpleFINPanel />)
    const fills = [...container.querySelectorAll<HTMLElement>('.sf-usage__fill')]
    expect(fills.map((f) => f.style.transform)).toEqual(['scaleX(0.5)', 'scaleX(0.5)'])
  })

  it('draws an empty bar, not NaN, for a zero limit', () => {
    status.current = served({ global_used: 0, global_limit: 0 })
    const { container } = render(<SimpleFINPanel />)
    const [global] = container.querySelectorAll<HTMLElement>('.sf-usage__fill')
    expect(global.style.transform).toBe('scaleX(0)')
  })
})
