/**
 * The date-range toolbar the ten explicit-range reports share.
 *
 * It offered seven fixed presets and no way to say "everything". The
 * months-based picker beside it had learned that windows should follow the
 * budget's own history; this had not, so the same question got two different
 * answers depending on which report you were looking at.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

const range = vi.hoisted(() => ({
  current: null as { earliest_month: string | null; months_available: number } | null,
}))
vi.mock('../../../api/reports', () => ({ useReportRange: () => ({ data: range.current }) }))
vi.mock('../../../stores/appStore', () => ({ useAppStore: () => 'b1' }))

import { DateRangePicker } from './DateRangePicker'
import { toISODate } from '../../../utils/dateWindow'

// The component's own formatter, deliberately. `new Date().toISOString()` is
// the UTC date, so this file failed every evening west of UTC — the same
// round-trip the picker itself stopped doing, left behind in its test.
const TODAY = toISODate(new Date())

function mount(onChange = vi.fn()) {
  render(<DateRangePicker startDate="2026-01-01" endDate="2026-01-31" onChange={onChange} />)
  return onChange
}

describe('DateRangePicker — All Time', () => {
  it('offers it once the budget has history', () => {
    range.current = { earliest_month: '2024-03-01', months_available: 30 }
    mount()
    expect(screen.getByRole('button', { name: 'All Time' })).toBeInTheDocument()
  })

  it('resolves to real dates rather than sending a sentinel', async () => {
    // Same discipline as the months picker: the server sees an ordinary
    // range, so no endpoint needs to learn what "all" means.
    range.current = { earliest_month: '2024-03-01', months_available: 30 }
    const onChange = mount()

    await userEvent.click(screen.getByRole('button', { name: 'All Time' }))

    expect(onChange).toHaveBeenCalledWith('2024-03-01', TODAY)
  })

  it('is hidden on a budget with no history, where it would be an empty range', () => {
    range.current = { earliest_month: null, months_available: 0 }
    mount()
    expect(screen.queryByRole('button', { name: 'All Time' })).toBeNull()
    // The fixed presets are unaffected.
    expect(screen.getByRole('button', { name: 'This Month' })).toBeInTheDocument()
  })

  it('is hidden while the span is still loading', () => {
    range.current = null
    mount()
    expect(screen.queryByRole('button', { name: 'All Time' })).toBeNull()
  })

  it('reads as the active preset when the dates match it', async () => {
    range.current = { earliest_month: '2024-03-01', months_available: 30 }
    const onChange = vi.fn()
    render(<DateRangePicker startDate="2024-03-01" endDate={TODAY} onChange={onChange} />)

    expect(screen.getByRole('button', { name: 'All Time' }).className).toContain(
      'drp__preset--active'
    )
  })
})
