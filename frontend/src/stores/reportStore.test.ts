/**
 * resolveGroupBy: tabs share one stored group-by, but not every tab can draw
 * every mode. "Payee" picked on the old Pareto reached the treemap as-is, which
 * silently drew group tiles under a highlighted Payee button — group names
 * where the user asked for payees.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  expensesDrill,
  filterSupport,
  incomeDrill,
  liveReportTab,
  liveReportTabs,
  openedTabState,
  planSpentDrill,
  REPORT_TABS,
  RETIRED_REPORT_TABS,
  resolveGroupBy,
  resolveWhereItWentView,
  useReportStore,
  type ReportFilters,
} from './reportStore'
import { lastMonthWindow } from '../utils/dateWindow'
import { PERSIST_KEYS } from './persistKeys'
import { pinTimeZone } from '../test-utils/timeZone'

describe('resolveGroupBy', () => {
  it('keeps a mode the tab can draw', () => {
    expect(resolveGroupBy('where-it-went', 'payee')).toBe('payee')
    expect(resolveGroupBy('spending-trends', 'group')).toBe('group')
    expect(resolveGroupBy('spending-trends', 'category')).toBe('category')
  })

  it('falls back when a tab without payee data is handed payee', () => {
    expect(resolveGroupBy('spending-trends', 'payee')).toBe('group')
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
    expect(planSpentDrill('cat-1', 'Groceries · Aug', window)).toEqual({
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
    expect(planSpentDrill('cat-1', 'Groceries', window).direction).toBeUndefined()
  })
})

describe('filterSupport', () => {
  // Where it went's modes read two reports. Every filter was lit in every mode
  // on the old Pareto, so a category picked in payee mode appeared to apply
  // while the bars ignored it.
  it('dims the payee filter where Where it went ranks categories or groups', () => {
    expect(filterSupport('where-it-went', 'category').payees).toBe(false)
    expect(filterSupport('where-it-went', 'group').payees).toBe(false)
    expect(filterSupport('where-it-went', 'category').categories).toBe(true)
    expect(filterSupport('where-it-went', 'group').views).toBe(true)
  })

  it('dims the category scope and the view where Where it went ranks payees', () => {
    const payee = filterSupport('where-it-went', 'payee')
    expect([payee.categories, payee.views, payee.payees]).toEqual([false, false, true])
  })

  it('leaves a tab without modes as declared', () => {
    expect(filterSupport('day-patterns', 'payee').categories).toBe(true)
  })
})

describe('resolveWhereItWentView', () => {
  it('draws the stored view in category and group mode', () => {
    expect(resolveWhereItWentView('treemap', 'category')).toBe('treemap')
    expect(resolveWhereItWentView('treemap', 'group')).toBe('treemap')
    expect(resolveWhereItWentView('table', 'group')).toBe('table')
  })

  it('draws the table in payee mode, which holds only the ranked 25', () => {
    // Twenty-five tiles would fill the whole area and read as all of it.
    expect(resolveWhereItWentView('treemap', 'payee')).toBe('table')
  })
})

/**
 * Breakdown, Pareto and Treemap became one report, Where it went. Their ids
 * live on in the persisted tab, in `?tab=` links, and in the starred list the
 * server stores without reading — each must reach the new report, showing
 * what the old tab showed.
 */
describe('retired report tabs', () => {
  const filters = (over: Partial<ReportFilters> = {}): ReportFilters => ({
    ...useReportStore.getState().filters,
    ...over,
  })

  it('points every retired id at a live tab, and no live id is retired', () => {
    const live = new Set<string>(REPORT_TABS.map((t) => t.id))
    for (const [id, retired] of Object.entries(RETIRED_REPORT_TABS)) {
      expect(live.has(retired.tab), id).toBe(true)
      expect(live.has(id), id).toBe(false)
    }
  })

  it('names the successor of each merged spending report', () => {
    expect(liveReportTab('spending-breakdown')).toBe('where-it-went')
    expect(liveReportTab('pareto')).toBe('where-it-went')
    expect(liveReportTab('treemap')).toBe('where-it-went')
    expect(liveReportTab('essentials')).toBe('essentials')
    expect(liveReportTab('debts')).toBeNull()
  })

  it('opens Pareto as the table in its own group-by, payee included', () => {
    for (const groupBy of ['group', 'category', 'payee'] as const) {
      expect(openedTabState('pareto', filters({ groupBy }))).toEqual({
        activeTab: 'where-it-went',
        whereItWentView: 'table',
      })
    }
  })

  it('opens the Treemap as the treemap, in the mode it was drawing', () => {
    expect(openedTabState('treemap', filters({ groupBy: 'category' }))).toEqual({
      activeTab: 'where-it-went',
      whereItWentView: 'treemap',
    })
    // It drew group tiles for a stored payee mode, having no payee data.
    expect(openedTabState('treemap', filters({ groupBy: 'payee' }))).toEqual({
      activeTab: 'where-it-went',
      whereItWentView: 'treemap',
      filters: { groupBy: 'group' },
    })
  })

  it('opens the Breakdown as the group table it was', () => {
    expect(openedTabState('spending-breakdown', filters({ groupBy: 'payee' }))).toEqual({
      activeTab: 'where-it-went',
      whereItWentView: 'table',
      filters: { groupBy: 'group' },
    })
  })

  it('opens a live id as itself and nothing for an unknown one', () => {
    expect(openedTabState('seasonality', filters())).toEqual({ activeTab: 'seasonality' })
    expect(openedTabState('debts', filters())).toBeNull()
  })

  it('maps a starred list to live tabs, once each, in the order starred', () => {
    // The server stores what the client sent and never reads it, so the old
    // ids are still in it. Dropping them lost the star; keeping them drew a
    // tab that no longer renders.
    expect(liveReportTabs(['essentials', 'pareto', 'net-worth', 'treemap', 'debts'])).toEqual([
      'essentials',
      'where-it-went',
      'net-worth',
    ])
    expect(liveReportTabs(['treemap', 'spending-breakdown', 'where-it-went'])).toEqual([
      'where-it-went',
    ])
    expect(liveReportTabs([])).toEqual([])
  })

  describe('in the store', () => {
    afterEach(() => {
      useReportStore.setState({ activeTab: 'overview', whereItWentView: 'table' })
      useReportStore.getState().setFilters({ groupBy: 'category' })
      localStorage.removeItem(PERSIST_KEYS.reports)
    })

    const persisted = (activeTab: string, groupBy: string, whereItWentView?: string) =>
      localStorage.setItem(
        PERSIST_KEYS.reports,
        JSON.stringify({
          state: {
            activeTab,
            filters: { ...filters(), groupBy },
            ...(whereItWentView ? { whereItWentView } : {}),
          },
          version: 1,
        })
      )

    it('reopens a persisted Pareto tab as Where it went, keeping payee mode', async () => {
      persisted('pareto', 'payee', 'treemap')
      await useReportStore.persist.rehydrate()
      const s = useReportStore.getState()
      expect([s.activeTab, s.whereItWentView, s.filters.groupBy]).toEqual([
        'where-it-went',
        'table',
        'payee',
      ])
    })

    it('reopens a persisted Treemap tab on the treemap view', async () => {
      persisted('treemap', 'category')
      await useReportStore.persist.rehydrate()
      const s = useReportStore.getState()
      expect([s.activeTab, s.whereItWentView, s.filters.groupBy]).toEqual([
        'where-it-went',
        'treemap',
        'category',
      ])
    })

    it('reopens a persisted Breakdown tab on the group table', async () => {
      persisted('spending-breakdown', 'category', 'treemap')
      await useReportStore.persist.rehydrate()
      const s = useReportStore.getState()
      expect([s.activeTab, s.whereItWentView, s.filters.groupBy]).toEqual([
        'where-it-went',
        'table',
        'group',
      ])
    })

    it('leaves a live persisted tab and its view alone', async () => {
      persisted('where-it-went', 'group', 'treemap')
      await useReportStore.persist.rehydrate()
      const s = useReportStore.getState()
      expect([s.activeTab, s.whereItWentView, s.filters.groupBy]).toEqual([
        'where-it-went',
        'treemap',
        'group',
      ])
    })

    it('opens a retired id from a link with its settings, and refuses an unknown one', () => {
      useReportStore.getState().setFilters({ groupBy: 'payee' })
      expect(useReportStore.getState().openTab('treemap')).toBe(true)
      const s = useReportStore.getState()
      expect([s.activeTab, s.whereItWentView, s.filters.groupBy]).toEqual([
        'where-it-went',
        'treemap',
        'group',
      ])
      expect(useReportStore.getState().openTab('debts')).toBe(false)
      expect(useReportStore.getState().activeTab).toBe('where-it-went')
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
