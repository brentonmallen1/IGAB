/**
 * resolveGroupBy: tabs share one stored group-by, but not every tab can draw
 * every mode. "Payee" picked on the pareto reached the treemap as-is, which
 * silently drew group tiles under a highlighted Payee button — group names
 * where the user asked for payees.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { incomeDrill, resolveGroupBy, useReportStore } from './reportStore'
import { thisMonthWindow } from '../utils/dateWindow'
import { pinTimeZone } from '../test-utils/timeZone'

describe('resolveGroupBy', () => {
  it('keeps a mode the tab can draw', () => {
    expect(resolveGroupBy('pareto', 'payee')).toBe('payee')
    expect(resolveGroupBy('treemap', 'group')).toBe('group')
    expect(resolveGroupBy('treemap', 'category')).toBe('category')
  })

  it('falls back when the treemap is handed payee', () => {
    expect(resolveGroupBy('treemap', 'payee')).toBe('group')
  })

  it('leaves tabs without a group-by control alone', () => {
    expect(resolveGroupBy('net-worth', 'payee')).toBe('payee')
  })
})

describe('incomeDrill', () => {
  // The Sankey's Income node drilled parent rows. A split paycheck of +1,000
  // pay and -300 fees is one +700 parent, so a node reading 1,000 opened a
  // list totalling 700. Income is leaf rows of the income class, everywhere.
  it('lists the leaf rows every income figure counts', () => {
    const window = { startDate: '2026-08-01', endDate: '2026-08-31' }
    expect(incomeDrill('Income', window)).toEqual({
      kind: 'month',
      label: 'Income',
      scope: 'leaf',
      direction: 'inflow',
      activityClasses: ['income'],
      ...window,
    })
  })
})

/**
 * The default report window is "this month so far". It was built as
 * `toISOString().slice(0, 10)` of a local month-start, which east of
 * Greenwich is the last day of the PREVIOUS month — at 00:30 on 1 September
 * in Berlin the reports asked the server for 31 August onwards, a day nobody
 * chose. Pinned to Berlin just after midnight on the 1st, the one moment that
 * shows it; in UTC the two versions agree.
 */
describe('resetFilters ahead of Greenwich', () => {
  pinTimeZone('Europe/Berlin')
  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts the default window on the 1st of the local month', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 1, 0, 30))

    useReportStore.getState().resetFilters()

    const { startDate, endDate } = useReportStore.getState().filters
    expect(startDate).toBe('2026-09-01')
    expect(endDate).toBe('2026-09-01')
  })

  it("is the same value as the date picker's This Month preset", () => {
    // The picker highlights a preset by string equality; a third spelling of
    // "this month" that drifted would leave the default matching no preset.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 17, 12, 0))

    useReportStore.getState().resetFilters()

    const { startDate, endDate } = useReportStore.getState().filters
    expect({ start: startDate, end: endDate }).toEqual(thisMonthWindow())
    expect(thisMonthWindow()).toEqual({ start: '2026-09-01', end: '2026-09-17' })
  })
})
