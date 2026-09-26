/**
 * resolveGroupBy: tabs share one stored group-by, but not every tab can draw
 * every mode. "Payee" picked on the pareto reached the treemap as-is, which
 * silently drew group tiles under a highlighted Payee button — group names
 * where the user asked for payees.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  expensesDrill,
  filterSupport,
  incomeDrill,
  resolveGroupBy,
  useReportStore,
} from './reportStore'
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

  it('lists the leaf rows of the classes the report served', () => {
    // The classes are the server's (`expense_classes`, `counted_classes`).
    // They were a client copy, `spendingDrillClasses`, kept "in step" with
    // the server's by a comment.
    expect(expensesDrill('Expenses · 2026-08', window, ['spending'])).toEqual({
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
    expect(expensesDrill('Expenses', window, ['spending']).direction).toBeUndefined()
  })
})

describe('filterSupport', () => {
  // Pareto's modes read two reports. Every filter was lit in every mode, so a
  // category picked in payee mode appeared to apply while the bars ignored it.
  it('dims the payee filter where Pareto ranks categories or groups', () => {
    expect(filterSupport('pareto', 'category').payees).toBe(false)
    expect(filterSupport('pareto', 'group').payees).toBe(false)
    expect(filterSupport('pareto', 'category').categories).toBe(true)
  })

  it('dims the category scope and the view where Pareto ranks payees', () => {
    const payee = filterSupport('pareto', 'payee')
    expect([payee.categories, payee.views, payee.payees]).toEqual([false, false, true])
  })

  it('leaves a tab without modes as declared', () => {
    expect(filterSupport('spending-breakdown', 'payee').categories).toBe(true)
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
