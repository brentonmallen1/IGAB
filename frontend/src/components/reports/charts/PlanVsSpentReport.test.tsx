/**
 * Plan vs Spent: what each envelope had, spent and left, carryover counted —
 * the matrix, its totals row and its Total column.
 *
 * Every figure is served; these hold the page to drawing them, and to each
 * drill opening exactly what its figure counts. The pure rules are in
 * planVsSpentCells.test.ts; the arithmetic is the backend's.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlanVsSpentReport as Report } from '../../../types'

const queryState = vi.hoisted(() => ({
  current: { data: undefined as unknown, isLoading: false, isError: false, refetch: () => {} },
}))
const hookCalls = vi.hoisted(() => [] as unknown[][])

vi.mock('../../../api/reports', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  usePlanVsSpentReport: (...args: unknown[]) => {
    hookCalls.push(args)
    return queryState.current
  },
  useReportRange: () => ({ data: undefined }),
}))

import { useReportStore } from '../../../stores/reportStore'
import { useAppStore } from '../../../stores/appStore'
import { PRIVACY_MASK } from '../../../utils/money'
import { PlanVsSpentReport } from './PlanVsSpentReport'

/** One month of an envelope: carried in, assigned, spent → left (the
 *  budget page's Available). Over when a dollar short. */
function cell(
  month: string,
  carried: number,
  assigned: number,
  spent: number,
  extra: Record<string, unknown> = {}
) {
  const funded = carried + assigned
  const left = funded - spent
  return {
    month,
    carried_in: carried,
    assigned,
    moved_in: 0,
    moved_out: 0,
    funded,
    spent,
    other: 0,
    left,
    overspent: Math.max(0, -left),
    over: left <= -1,
    active: true,
    estimated: false,
    ...extra,
  }
}

function quiet(month: string) {
  return { ...cell(month, 0, 0, 0), active: false }
}

/** Dining: 40 short in June (covered), 10 left in July, and the 10 carried
 *  through a quiet August (running). Rent: 27 cents short in July — within
 *  the tolerance. Medical: a bill paid by 2,000 moved in from savings. */
const DATA: Report = {
  months: ['2026-06-01', '2026-07-01', '2026-08-01'],
  running_month: '2026-08-01',
  totals_start: '2026-06-01',
  totals_end: '2026-07-31',
  categories: [
    {
      category_id: 'c1',
      category_name: 'Dining',
      category_group_name: 'Everyday',
      monthly: [
        cell('2026-06-01', 0, 100, 140),
        cell('2026-07-01', 0, 100, 90),
        cell('2026-08-01', 10, 0, 0),
      ],
      months_over: 1,
      months_active: 2,
      avg_overspend: 40,
      chronic: true,
      total: {
        carried_in: 0,
        assigned: 200,
        moved_in: 0,
        moved_out: 0,
        funded: 200,
        spent: 230,
        other: 0,
        left: 10,
        overspent: 40,
        over: true,
        estimated: false,
      },
    },
    {
      category_id: 'c2',
      category_name: 'Rent',
      category_group_name: 'Home',
      monthly: [
        cell('2026-06-01', 0, 900, 900),
        cell('2026-07-01', 0, 900, 900.27, { over: false }),
        cell('2026-08-01', 0, 900, 900),
      ],
      months_over: 0,
      months_active: 2,
      avg_overspend: 0,
      chronic: false,
      total: {
        carried_in: 0,
        assigned: 1800,
        moved_in: 0,
        moved_out: 0,
        funded: 1800,
        spent: 1800.27,
        other: 0,
        left: 0,
        overspent: 0.27,
        over: false,
        estimated: false,
      },
    },
    {
      category_id: 'c3',
      category_name: 'Medical',
      category_group_name: 'Health',
      monthly: [
        cell('2026-06-01', 0, 0, 2000, { moved_in: 2000, funded: 2000, left: 0, over: false }),
        quiet('2026-07-01'),
        quiet('2026-08-01'),
      ],
      months_over: 0,
      months_active: 1,
      avg_overspend: 0,
      chronic: false,
      total: {
        carried_in: 0,
        assigned: 0,
        moved_in: 2000,
        moved_out: 0,
        funded: 2000,
        spent: 2000,
        other: 0,
        left: 0,
        overspent: 0,
        over: false,
        estimated: false,
      },
    },
  ],
  month_totals: [
    {
      month: '2026-06-01',
      partial_month: false,
      carried_in: 0,
      assigned: 1000,
      moved_in: 2000,
      moved_out: 0,
      funded: 3000,
      spent: 3040,
      other: 0,
      left: -40,
      overspent: 40,
      categories_over: 1,
    },
    {
      month: '2026-07-01',
      partial_month: false,
      carried_in: 0,
      assigned: 1000,
      moved_in: 0,
      moved_out: 0,
      funded: 1000,
      spent: 990.27,
      other: 0,
      left: 9.73,
      overspent: 0.27,
      categories_over: 0,
    },
    {
      month: '2026-08-01',
      partial_month: true,
      carried_in: 10,
      assigned: 900,
      moved_in: 0,
      moved_out: 0,
      funded: 910,
      spent: 900,
      other: 0,
      left: 10,
      overspent: 0,
      categories_over: 0,
    },
  ],
  total_assigned: 2000,
  total_moved_in: 2000,
  total_moved_out: 0,
  total_funded: 4000,
  total_spent: 4030.27,
  total_other: 0,
  total_left: 10,
  total_overspent: 40.27,
  chronic_count: 1,
  filter_unavailable: false,
}

function show(data: unknown = DATA) {
  queryState.current = { data, isLoading: false, isError: false, refetch: () => {} }
  return render(
    <MemoryRouter>
      <PlanVsSpentReport budgetId="b1" />
    </MemoryRouter>
  )
}

/** The row whose header names `label`: its data cells' text. */
function rowCells(label: string): HTMLTableCellElement[] {
  const header = screen.getAllByText(label).find((el) => el.closest('tr'))
  return [...(header?.closest('tr')?.querySelectorAll('td') ?? [])]
}

function card(label: string): string {
  const el = screen.getByText(label, { selector: '.metric-card__label' }).closest('.metric-card')
  return el?.querySelector('.metric-card__value')?.textContent ?? ''
}

beforeEach(() => {
  hookCalls.length = 0
  useReportStore.getState().setDrillDown(null)
})

afterEach(() => {
  useAppStore.setState({ privacyMode: false })
  useReportStore.getState().setFilters({ categoryIds: [], tagIds: [], filterId: null })
})

describe('the matrix', () => {
  it('draws what each envelope had left, the over count and the Total column', () => {
    show()
    expect(rowCells('Dining').map((c) => c.textContent)).toEqual([
      '−40',
      '10',
      // August holds July's 10 with nothing moving: a balance, not a blank.
      '10',
      '1/2',
      '$200.00',
      '$230.00',
      '−40',
    ])
  })

  it('marks chronic with a dot the legend explains, named for a screen reader', () => {
    const { container } = show()
    expect(container.querySelectorAll('[data-testid="chronic-dot"]')).toHaveLength(1)
    expect(screen.getByRole('button', { name: /^Chronic:\s*Dining/ })).toBeInTheDocument()
    expect(container.querySelector('.plan-spent__legend')?.textContent).toContain(
      'went negative in 3 of the last 6 months'
    )
    // The word no longer rides on every row as a pill.
    expect(container.querySelector('.plan-spent__badge')).toBeNull()
  })

  it('marks the running month "so far"', () => {
    const { container } = show()
    const headers = [...container.querySelectorAll('th.plan-spent__month-header')]
    expect(headers.map((h) => h.textContent?.includes('so far'))).toEqual([false, false, true])
  })

  it('draws a few cents short as nothing: no "−0", no tint', () => {
    const { container } = show()
    expect(screen.queryByText('−0')).toBeNull()
    // Dining's June, and Dining's Total: the two served verdicts of "over".
    expect(container.querySelectorAll('td.plan-spent__cell--over')).toHaveLength(2)
  })

  it('opens scrolled to the newest month', () => {
    // On a phone only two or three months fit, and it opened on last year.
    const widths = vi.spyOn(HTMLElement.prototype, 'scrollWidth', 'get').mockReturnValue(1200)
    try {
      const { container } = show()
      const scroller = container.querySelector('.plan-spent__scroll') as HTMLElement
      expect(scroller.scrollLeft).toBe(1200)
    } finally {
      widths.mockRestore()
    }
  })

  it('pins the name column and the four totals columns on every row', () => {
    const { container } = show()
    // The CSS pins these; the markup must use them on every row — header,
    // body and footer — or a figure scrolls away from its name or its total.
    const rows = container.querySelectorAll('thead tr, tbody tr, tfoot tr')
    expect(rows.length).toBe(5)
    for (const row of rows) {
      expect(row.querySelector('.plan-spent__name')).not.toBeNull()
      expect(row.querySelectorAll('.plan-spent__tot')).toHaveLength(4)
    }
  })

  it('filters to chronic categories only', () => {
    show()
    fireEvent.click(screen.getByLabelText('Chronic only'))
    expect(screen.getByRole('button', { name: /Dining/ })).toBeInTheDocument()
    expect(screen.queryByText('Rent')).not.toBeInTheDocument()
  })

  it('ranks what Ready to Assign covered most first on request', () => {
    const { container } = show()
    fireEvent.click(screen.getByRole('button', { name: 'Sort by overspent' }))
    const names = [...container.querySelectorAll('tbody .plan-spent__name-cat')].map(
      (n) => n.textContent
    )
    expect(names).toEqual(['Dining', 'Rent', 'Medical'])
  })

  it('has no Running total toggle', () => {
    // It drew a cumulative row below the fold and read as doing nothing.
    show()
    expect(screen.queryByLabelText('Running total')).toBeNull()
  })

  it('titles a cell with how it adds up, carryover first', () => {
    show()
    expect(rowCells('Dining')[1].getAttribute('title')).toContain(
      'carried in $0.00 · assigned $100.00 · spent $90.00 · left $10.00'
    )
    expect(rowCells('Dining')[0].getAttribute('title')).toContain('$40.00 short')
  })
})

describe('the headline', () => {
  it('answers in one line: chronic, over last month, most over', () => {
    const { container } = show()
    const line = container.querySelector('.plan-spent__headline')?.textContent
    // July is the last complete month and nothing went over in it.
    expect(line).toContain('1 chronic')
    expect(line).toContain('0 over in')
    expect(line).toContain('most over: Dining')
  })

  it('states funded, spent, what Ready to Assign covered, and what is left', () => {
    show()
    expect(card('Funded')).toBe('$4,000.00')
    expect(card('Spent')).toBe('$4,030.27')
    expect(card('Overspent')).toBe('$40.27')
    expect(card('Left')).toBe('$10.00')
  })

  it('says carryover is included, once', () => {
    show()
    expect(screen.getAllByText(/carryover included/)).toHaveLength(1)
  })
})

describe('the Total column', () => {
  it('is the category over the complete months: funded, spent and what was covered', () => {
    show()
    const cells = rowCells('Dining').map((c) => c.textContent)
    expect(cells.slice(-4)).toEqual(['1/2', '$200.00', '$230.00', '−40'])
  })

  it('titles the Total with how its sum closes', () => {
    // 2,000 moved in from savings paid a 2,000 bill: funded, not overspent.
    show()
    expect(rowCells('Medical').at(-1)?.getAttribute('title')).toContain(
      'carried in $0.00 · moved in $2,000.00 · spent $2,000.00 · left $0.00'
    )
    expect(rowCells('Dining').at(-1)?.getAttribute('title')).toContain(
      'Ready to Assign covered $40.00 · left $10.00'
    )
  })

  it('tints a total the server calls over, and only that', () => {
    show()
    const [dining, rent] = [rowCells('Dining').at(-1), rowCells('Rent').at(-1)]
    expect(dining?.style.background).toContain('--chart-negative')
    expect(rent?.style.background).toBe('')
  })
})

describe('the totals row', () => {
  it('is what Ready to Assign covered each month, the running month drawn apart', () => {
    show()
    const cells = rowCells('Overspent, all categories')
    expect(cells.slice(0, 3).map((c) => c.textContent)).toEqual(['−40', '0', '—'])
    expect(cells[0].className).toContain('plan-spent__foot--over')
    // 27 cents is covered, and no category counts as over for it.
    expect(cells[1].className).toContain('plan-spent__foot--quiet')
    expect(cells[2].className).toContain('plan-spent__cell--running')
    // The window's own totals close the row, meeting the Overspent column.
    expect(cells.slice(-3).map((c) => c.textContent)).toEqual(['$4,000.00', '$4,030.27', '−40'])
  })
})

describe('each figure opens what it counts', () => {
  const drill = () => useReportStore.getState().drillDown

  it('a cell: the category, that month, the plan ledger both ways', () => {
    show()
    fireEvent.click(rowCells('Dining')[0])
    expect(drill()).toMatchObject({
      categoryIds: ['c1'],
      planSpent: true,
      scope: 'leaf',
      startDate: '2026-06-01',
      endDate: '2026-06-30',
    })
    expect(drill()?.direction).toBeUndefined()
  })

  it('a Total, and the category name: the category over the complete months', () => {
    show()
    fireEvent.click(rowCells('Dining').at(-1)!)
    const window = { categoryIds: ['c1'], startDate: '2026-06-01', endDate: '2026-07-31' }
    expect(drill()).toMatchObject({ ...window, planSpent: true })
    useReportStore.getState().setDrillDown(null)
    fireEvent.click(screen.getByRole('button', { name: /Dining/ }))
    expect(drill()).toMatchObject(window)
  })

  it('a month total: every category in the report, that month', () => {
    show()
    fireEvent.click(rowCells('Overspent, all categories')[0])
    expect(drill()).toMatchObject({
      planSpent: true,
      startDate: '2026-06-01',
      endDate: '2026-06-30',
    })
    // Every category: no one category's ids, which would list a subset.
    expect(drill()?.categoryIds).toBeUndefined()
  })

  it("a month total under a scope: the report's scope, not the whole budget", () => {
    useReportStore.getState().setFilters({ tagIds: ['t1'] })
    show()
    fireEvent.click(rowCells('Overspent, all categories')[1])
    expect(drill()).toMatchObject({ tagIds: ['t1'], planSpent: true, startDate: '2026-07-01' })
  })

  it("the window's Spent: every category over the complete months", () => {
    show()
    fireEvent.click(rowCells('Overspent, all categories').at(-2)!)
    expect(drill()).toMatchObject({
      planSpent: true,
      startDate: '2026-06-01',
      endDate: '2026-07-31',
    })
  })

  it('opens no total before a month has closed', () => {
    show({ ...DATA, totals_start: null, totals_end: null })
    fireEvent.click(rowCells('Dining').at(-1)!)
    expect(drill()).toBeNull()
  })
})

describe('scope', () => {
  it('asks for the tags and the saved filter the filter bar offers', () => {
    useReportStore.getState().setFilters({ categoryIds: [], tagIds: ['t1'], filterId: 'f1' })
    show()
    const [, , scope] = hookCalls.at(-1)!
    expect(scope).toEqual({ categoryIds: [], tagIds: ['t1'], filterId: 'f1' })
  })

  it('says so when the saved filter it was asked for is gone', () => {
    show({ ...DATA, filter_unavailable: true })
    expect(screen.getByText(/That saved filter no longer exists/)).toBeInTheDocument()
  })
})

describe('in privacy mode', () => {
  it('masks every figure the matrix draws itself, sign and zero included', () => {
    // The matrix draws its own labels, outside useFormatters. Its privacy
    // argument once went unpassed at no test's notice, and with it passed the
    // sign still sat outside the mask: "−••••", "+••••" and a bare "0".
    useAppStore.setState({ privacyMode: true })
    const { container } = show()
    const drawn = [...container.querySelectorAll('td.plan-spent__cell')].filter(
      (c) => c.textContent !== ''
    )
    expect(drawn.length).toBeGreaterThan(8)
    for (const c of drawn) expect(c.textContent).toBe(PRIVACY_MASK)
  })

  it('keeps the overspend tint, which shows state rather than a figure', () => {
    useAppStore.setState({ privacyMode: true })
    const { container } = show()
    const over = container.querySelectorAll('tbody td.plan-spent__cell--over')
    expect((over[0] as HTMLElement).style.background).toContain('--chart-negative')
  })
})
