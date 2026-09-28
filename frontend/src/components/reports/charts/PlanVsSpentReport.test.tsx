/**
 * Plan vs Spent: the matrix, its totals row and its Total column — one report
 * where Budget vs Actual, Cumulative Variance and Plan vs Reality were three.
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

function cell(month: string, plan: number, spent: number, extra: Record<string, unknown> = {}) {
  const variance = plan - spent
  return {
    month,
    assigned: plan,
    moved_in: 0,
    moved_out: 0,
    plan,
    spent,
    variance,
    over: variance <= -1,
    active: true,
    ...extra,
  }
}

const QUIET = { assigned: 0, moved_in: 0, moved_out: 0, plan: 0, spent: 0, variance: 0 }

/** Dining: 40 over in June, 10 under in July, quiet in August (running).
 *  Rent: on plan, 27 cents over in July — on plan by the tolerance. Medical:
 *  a bill paid by 2,000 moved in from savings. */
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
        cell('2026-06-01', 100, 140),
        cell('2026-07-01', 100, 90),
        { month: '2026-08-01', ...QUIET, over: false, active: false },
      ],
      months_over: 1,
      months_active: 2,
      avg_overspend: 40,
      chronic: true,
      sinking_fund: false,
      total: {
        assigned: 200,
        moved_in: 0,
        moved_out: 0,
        plan: 200,
        spent: 230,
        variance: -30,
        variance_pct: -15,
        over: true,
      },
    },
    {
      category_id: 'c2',
      category_name: 'Rent',
      category_group_name: 'Home',
      monthly: [
        cell('2026-06-01', 900, 900),
        cell('2026-07-01', 900, 900.27, { over: false }),
        cell('2026-08-01', 900, 900),
      ],
      months_over: 0,
      months_active: 2,
      avg_overspend: 0,
      chronic: false,
      sinking_fund: false,
      total: {
        assigned: 1800,
        moved_in: 0,
        moved_out: 0,
        plan: 1800,
        spent: 1800.27,
        variance: -0.27,
        variance_pct: -0.015,
        over: false,
      },
    },
    {
      category_id: 'c3',
      category_name: 'Medical',
      category_group_name: 'Health',
      monthly: [
        cell('2026-06-01', 2000, 2000, { assigned: 0, moved_in: 2000 }),
        { month: '2026-07-01', ...QUIET, over: false, active: false },
        { month: '2026-08-01', ...QUIET, over: false, active: false },
      ],
      months_over: 0,
      months_active: 1,
      avg_overspend: 0,
      chronic: false,
      sinking_fund: false,
      total: {
        assigned: 0,
        moved_in: 2000,
        moved_out: 0,
        plan: 2000,
        spent: 2000,
        variance: 0,
        variance_pct: 0,
        over: false,
      },
    },
  ],
  month_totals: [
    {
      month: '2026-06-01',
      partial_month: false,
      assigned: 1000,
      moved_in: 2000,
      moved_out: 0,
      plan: 3000,
      spent: 3040,
      variance: -40,
      cumulative_variance: -40,
      categories_over: 1,
    },
    {
      month: '2026-07-01',
      partial_month: false,
      assigned: 1000,
      moved_in: 0,
      moved_out: 0,
      plan: 1000,
      spent: 990.27,
      variance: 9.73,
      cumulative_variance: -30.27,
      categories_over: 0,
    },
    {
      month: '2026-08-01',
      partial_month: true,
      assigned: 900,
      moved_in: 0,
      moved_out: 0,
      plan: 900,
      spent: 900,
      variance: 0,
      cumulative_variance: null,
      categories_over: 0,
    },
  ],
  total_assigned: 2000,
  total_moved_in: 2000,
  total_moved_out: 0,
  total_plan: 4000,
  total_spent: 4030.27,
  total_variance: -30.27,
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
  it('draws variance cells, the over count and the chronic badge', () => {
    show()
    expect(screen.getAllByText('Chronic').length).toBeGreaterThan(0)
    expect(rowCells('Dining').map((c) => c.textContent)).toEqual([
      '−40',
      '+10',
      '',
      '1/2',
      '$200.00',
      '$230.00',
      '−30',
    ])
  })

  it('marks the running month "so far"', () => {
    const { container } = show()
    const headers = [...container.querySelectorAll('th.plan-spent__month-header')]
    expect(headers.map((h) => h.textContent?.includes('so far'))).toEqual([false, false, true])
  })

  it('draws a few cents over as on plan: no "−0", no tint', () => {
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

  it('keeps the category column sticky', () => {
    const { container } = show()
    // The CSS pins these; the markup must use them on every row, the totals
    // rows included, or a name scrolls away from its figures.
    const rows = container.querySelectorAll('tbody tr, tfoot tr')
    for (const row of rows) expect(row.querySelector('.plan-spent__cat-cell')).not.toBeNull()
  })

  it('filters to chronic categories only', () => {
    show()
    fireEvent.click(screen.getByLabelText('Chronic only'))
    expect(screen.getByRole('button', { name: /Dining/ })).toBeInTheDocument()
    expect(screen.queryByText('Rent')).not.toBeInTheDocument()
  })

  it('ranks the biggest overrun first on request', () => {
    const { container } = show()
    fireEvent.click(screen.getByRole('button', { name: 'Sort by overspent' }))
    const names = [...container.querySelectorAll('tbody .plan-spent__cat-name')].map(
      (n) => n.textContent
    )
    expect(names).toEqual(['Dining', 'Rent', 'Medical'])
  })
})

describe('the headline', () => {
  it('answers in one line: chronic, over last month, most over', () => {
    const { container } = show()
    const line = container.querySelector('.plan-spent__headline')?.textContent
    // June: July is the last complete month and nothing was over in it...
    expect(line).toContain('1 chronic')
    expect(line).toContain('0 over in')
    expect(line).toContain('most over: Dining')
  })

  it('states the window totals, the variance with its direction in words', () => {
    show()
    expect(card('Planned')).toBe('$4,000.00')
    expect(card('Spent')).toBe('$4,030.27')
    expect(card('Over plan by')).toBe('$30.27')
  })

  it('says carryover is ignored, once', () => {
    show()
    expect(screen.getAllByText(/carryover ignored/)).toHaveLength(1)
  })
})

describe('the Total column', () => {
  it('is the category over the complete months: planned, spent and the verdict', () => {
    show()
    const cells = rowCells('Dining').map((c) => c.textContent)
    expect(cells.slice(-4)).toEqual(['1/2', '$200.00', '$230.00', '−30'])
  })

  it('names what moved the plan, as Budget vs Actual did', () => {
    // 2,000 moved in from savings paid a 2,000 bill. Against the raw
    // assignment it read a 2,000 overrun.
    show()
    const planned = rowCells('Medical').at(-3)
    expect(planned?.getAttribute('title')).toBe(
      'planned $2,000.00 (assigned $0.00 + moved in $2,000.00)'
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
  it('is each month across every category, with the running month drawn apart', () => {
    show()
    const cells = rowCells('All categories')
    expect(cells.slice(0, 3).map((c) => c.textContent)).toEqual(['−40', '+10', '0'])
    expect(cells[0].className).toContain('plan-spent__month-total--over')
    expect(cells[2].className).toContain('plan-spent__cell--running')
    // The window's own totals close the row.
    expect(cells.slice(-3).map((c) => c.textContent)).toEqual(['$4,000.00', '$4,030.27', '−30'])
  })

  it('says why the bottom row and the Total column end apart, only when they do', () => {
    const { container, unmount } = show()
    expect(container.querySelector('.plan-spent__grain-note')).toBeNull()
    unmount()
    show({ ...DATA, total_variance: -330.27 })
    expect(
      screen.getByText(/adds up to -?\$30\.27; the Total column says -?\$330\.27/)
    ).toBeInTheDocument()
  })

  it('shows the running total on request, with none for the month in progress', () => {
    show()
    expect(screen.queryByText('Running total', { selector: 'th' })).toBeNull()
    fireEvent.click(screen.getByLabelText('Running total'))
    const cells = rowCells('Running total')
    expect(cells.slice(0, 3).map((c) => c.textContent)).toEqual(['−40', '−30', '—'])
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
    fireEvent.click(rowCells('All categories')[0])
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
    fireEvent.click(rowCells('All categories')[1])
    expect(drill()).toMatchObject({ tagIds: ['t1'], planSpent: true, startDate: '2026-07-01' })
  })

  it("the window's Spent: every category over the complete months", () => {
    show()
    fireEvent.click(rowCells('All categories').at(-2)!)
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
