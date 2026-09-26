/**
 * resolveGroupBy: tabs share one stored group-by, but not every tab can draw
 * every mode. "Payee" picked on the pareto reached the treemap as-is, which
 * silently drew group tiles under a highlighted Payee button — group names
 * where the user asked for payees.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expensesDrill, incomeDrill, resolveGroupBy, useReportStore } from './reportStore'
import { lastMonthWindow } from '../utils/dateWindow'
import { PERSIST_KEYS } from './persistKeys'
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
      activityClasses: ['income'],
      ...window,
    })
  })

  it('lists a clawed-back paycheck, which the Income figure nets', () => {
    // `direction: 'inflow'` dropped it, so the list was larger than the bar.
    expect(incomeDrill('Income', { startDate: '', endDate: '' }).direction).toBeUndefined()
  })
})

describe('expensesDrill', () => {
  const window = { startDate: '2026-08-01', endDate: '2026-08-31' }

  it('lists the spending-class leaf rows the Expenses figure nets', () => {
    expect(expensesDrill('Expenses · 2026-08', window)).toEqual({
      kind: 'month',
      label: 'Expenses · 2026-08',
      scope: 'leaf',
      activityClasses: ['spending'],
      ...window,
    })
  })

  it('keeps the refunds, so the list totals the bar', () => {
    // Income vs Expenses passed `direction: 'outflow'`: a bar of 15,300 net
    // opened 19,400 of purchases with the 4,100 of refunds left out.
    expect(expensesDrill('Expenses', window).direction).toBeUndefined()
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

  it('defaults to the last complete month, on the local 1st too', () => {
    // A month in progress is half a month: the Overview opened on "This
    // Month" and read "105% over income" with one paycheck of two in.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 1, 0, 30))

    useReportStore.getState().resetFilters()

    const { startDate, endDate } = useReportStore.getState().filters
    expect(startDate).toBe('2026-08-01')
    expect(endDate).toBe('2026-08-31')
  })

  it("is the same value as the date picker's Last Month preset", () => {
    // The picker highlights a preset by string equality; a third spelling of
    // "last month" that drifted would leave the default matching no preset.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 17, 12, 0))

    useReportStore.getState().resetFilters()

    const { startDate, endDate } = useReportStore.getState().filters
    expect({ start: startDate, end: endDate }).toEqual(lastMonthWindow())
    expect(lastMonthWindow()).toEqual({ start: '2026-08-01', end: '2026-08-31' })
  })

  it('moves a range stored before the default changed onto the new default once', async () => {
    // A stored range is dates, not a preset: "This Month" saved last week
    // would otherwise stay a running month on every visit.
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 8, 17, 12, 0))
    localStorage.setItem(
      PERSIST_KEYS.reports,
      JSON.stringify({
        state: { filters: { startDate: '2026-09-01', endDate: '2026-09-10' } },
        version: 0,
      })
    )
    await useReportStore.persist.rehydrate()
    const { startDate, endDate } = useReportStore.getState().filters
    expect({ startDate, endDate }).toEqual({ startDate: '2026-08-01', endDate: '2026-08-31' })
    localStorage.removeItem(PERSIST_KEYS.reports)
  })
})
