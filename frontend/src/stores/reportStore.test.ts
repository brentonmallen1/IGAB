/**
 * resolveGroupBy: tabs share one stored group-by, but not every tab can draw
 * every mode. "Payee" picked on the pareto reached the treemap as-is, which
 * silently drew group tiles under a highlighted Payee button — group names
 * where the user asked for payees.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  currentFavorites,
  currentReportTab,
  expensesDrill,
  filterSupport,
  incomeDrill,
  planSpentDrill,
  REPORT_TABS,
  resolveGroupBy,
  retiredReportTabs,
  useReportStore,
} from './reportStore'
import { REPORT_CATALOG } from '../components/reports/reportCatalog'
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

describe('planSpentDrill', () => {
  const window = { startDate: '2026-08-01', endDate: '2026-08-31' }

  it("lists the plan ledger's spent rows of one category, by the server's rule", () => {
    expect(planSpentDrill({ categoryIds: ['cat-1'] }, 'Groceries · Aug', window)).toEqual({
      kind: 'category',
      label: 'Groceries · Aug',
      scope: 'leaf',
      categoryIds: ['cat-1'],
      planSpent: true,
      ...window,
    })
  })

  it('keeps the refunds, so the list totals the figure', () => {
    // Budget vs Actual, Plan vs Reality, Volatility and Anomalies each passed
    // `direction: 'outflow'`: a cell of 70 net opened 100 of purchases.
    expect(
      planSpentDrill({ categoryIds: ['cat-1'] }, 'Groceries', window).direction
    ).toBeUndefined()
  })

  it("opens a month total over the report's own scope, every category in it", () => {
    // A Plan vs Spent month total covers every category the report does: with
    // a tag scoped, the tag; with nothing scoped, no category filter at all.
    expect(planSpentDrill({ tagIds: ['t-1'] }, 'Aug 26', window)).toMatchObject({
      tagIds: ['t-1'],
      planSpent: true,
    })
    expect(planSpentDrill({}, 'Aug 26', window).categoryIds).toBeUndefined()
  })
})

describe('retired report tabs', () => {
  it('maps the three plan reports to Plan vs Spent', () => {
    for (const old of ['budget-actual', 'variance', 'plan-reality']) {
      expect(currentReportTab(old)).toBe('plan-vs-spent')
    }
  })

  it('names only reports this build draws, and never a live id', () => {
    const live = new Set<string>(REPORT_TABS.map((t) => t.id))
    for (const [old, successor] of Object.entries(retiredReportTabs)) {
      expect(live.has(old)).toBe(false)
      expect(live.has(successor)).toBe(true)
    }
  })

  it('passes a live id through and refuses one it never knew', () => {
    expect(currentReportTab('savings')).toBe('savings')
    expect(currentReportTab('debts')).toBeNull()
    // An own key only: an object's prototype is not a report.
    expect(currentReportTab('constructor')).toBeNull()
  })

  it('keeps a starred retired report as its successor, once, in order', () => {
    // Two of the three plan reports starred: one star, where the first stood.
    expect(
      currentFavorites(['savings', 'budget-actual', 'essentials', 'plan-reality', 'debts'])
    ).toEqual(['savings', 'plan-vs-spent', 'essentials'])
    expect(currentFavorites(['plan-vs-spent', 'variance'])).toEqual(['plan-vs-spent'])
  })

  it('has one catalog entry for the one report', () => {
    expect(REPORT_CATALOG['plan-vs-spent'].summary).toBeTruthy()
    for (const old of Object.keys(retiredReportTabs)) expect(old in REPORT_CATALOG).toBe(false)
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

describe('a stored tab of a retired report', () => {
  afterEach(() => {
    localStorage.removeItem(PERSIST_KEYS.reports)
  })

  async function rehydrateWith(activeTab: string) {
    localStorage.setItem(PERSIST_KEYS.reports, JSON.stringify({ state: { activeTab }, version: 1 }))
    await useReportStore.persist.rehydrate()
    return useReportStore.getState().activeTab
  }

  it.each(['budget-actual', 'variance', 'plan-reality'])(
    'opens Plan vs Spent for %s',
    async (old) => {
      // It fell to the Overview: the page's stale-id guard knew only that the
      // id was gone, not what replaced it.
      expect(await rehydrateWith(old)).toBe('plan-vs-spent')
    }
  )

  it('keeps a live tab, and drops an unknown one to the Overview', async () => {
    expect(await rehydrateWith('essentials')).toBe('essentials')
    expect(await rehydrateWith('debts')).toBe('overview')
  })
})
