import { describe, expect, it } from 'vitest'
import {
  cellLabel,
  exportRows,
  monthTotalTone,
  overspendStyle,
  planVsSpentHeadline,
  totalShareLabel,
  varianceHeadline,
  worstOverspend,
  worstTotalOverspend,
} from './planVsSpentCells'
import { PRIVACY_MASK } from '../../../utils/money'
import type {
  PlanVsSpentCategory,
  PlanVsSpentCell,
  PlanVsSpentMonth,
  PlanVsSpentReport,
  PlanVsSpentTotal,
} from '../../../types'

function cell(month: string, variance: number, over = variance <= -1): PlanVsSpentCell {
  return {
    month,
    assigned: 100,
    moved_in: 0,
    moved_out: 0,
    plan: 100,
    spent: 100 - variance,
    variance,
    over,
    active: true,
  }
}

function total(variance: number, over = variance <= -1): PlanVsSpentTotal {
  return {
    assigned: 300,
    moved_in: 0,
    moved_out: 0,
    plan: 300,
    spent: 300 - variance,
    variance,
    variance_pct: (variance / 300) * 100,
    over,
  }
}

function category(
  name: string,
  monthly: PlanVsSpentCell[],
  extra: Partial<PlanVsSpentCategory> = {}
): PlanVsSpentCategory {
  const overs = monthly.filter((m) => m.over)
  return {
    category_id: name,
    category_name: name,
    category_group_name: 'Everyday',
    monthly,
    months_over: overs.length,
    months_active: monthly.length,
    avg_overspend: overs.length ? -overs.reduce((s, m) => s + m.variance, 0) / overs.length : 0,
    chronic: false,
    sinking_fund: false,
    total: total(0),
    ...extra,
  }
}

const MONTHS = ['2026-07-01', '2026-08-01', '2026-09-01']

function monthTotal(month: string, over: number, variance = 0): PlanVsSpentMonth {
  return {
    month,
    partial_month: month === '2026-09-01',
    assigned: 0,
    moved_in: 0,
    moved_out: 0,
    plan: 0,
    spent: 0,
    variance,
    cumulative_variance: month === '2026-09-01' ? null : variance,
    categories_over: over,
  }
}

function report(
  categories: PlanVsSpentCategory[],
  overByMonth: number[] = [0, 0, 0]
): PlanVsSpentReport {
  return {
    months: MONTHS,
    running_month: '2026-09-01',
    totals_start: '2026-07-01',
    totals_end: '2026-08-31',
    categories,
    month_totals: MONTHS.map((m, i) => monthTotal(m, overByMonth[i])),
    total_assigned: 0,
    total_moved_in: 0,
    total_moved_out: 0,
    total_plan: 0,
    total_spent: 0,
    total_variance: 0,
    chronic_count: categories.filter((c) => c.chronic).length,
    filter_unavailable: false,
  }
}

describe('cellLabel', () => {
  it('signs the variance and abbreviates it', () => {
    expect(cellLabel(-40, false)).toBe('−40')
    expect(cellLabel(10, false)).toBe('+10')
    expect(cellLabel(4180, false)).toBe('+4.2k')
    expect(cellLabel(0, false)).toBe('0')
  })

  it('never signs a figure that rounds to nothing', () => {
    // A few cents past the plan read "−0", an overspend too small to show,
    // beside a flag that said the month was on plan.
    expect(cellLabel(-0.27, false)).toBe('0')
    expect(cellLabel(0.3, false)).toBe('0')
    expect(cellLabel(-0.6, false)).toBe('−1')
  })

  it('is the mask alone in privacy mode, sign and zero included', () => {
    // It put the sign outside the mask — "−••••" over plan, "+••••" under —
    // and printed an on-plan month as a literal "0", so the overspend could
    // be read straight off the grid.
    for (const v of [-40, 10, 0, -4180]) expect(cellLabel(v, true)).toBe(PRIVACY_MASK)
  })
})

describe('overspendStyle', () => {
  it('tints only a month the server calls over, deeper for the worst on screen', () => {
    expect(overspendStyle(cell('2026-09-01', 10), 40)).toEqual({})
    expect(overspendStyle(cell('2026-09-01', 0), 40)).toEqual({})
    expect(overspendStyle(cell('2026-09-01', -40), 40).background).toContain('38%')
    expect(overspendStyle(cell('2026-09-01', -20), 40).background).toContain('23%')
  })

  it('does not tint a negative variance inside the tolerance', () => {
    // 14 over a 1,500 mortgage is past a dollar and short of 1%: on plan. The
    // tint read the sign, and painted it as an overspend.
    expect(overspendStyle(cell('2026-09-01', -14, false), 40)).toEqual({})
  })

  it('tints a Total by its own verdict', () => {
    expect(overspendStyle(total(-90), 90).background).toContain('38%')
    expect(overspendStyle(total(-14, false), 90)).toEqual({})
  })
})

describe('worstOverspend', () => {
  it('scales to the worst over month, ignoring tolerated ones', () => {
    const cats = [category('A', [cell('2026-08-01', -30), cell('2026-09-01', -90, false)])]
    expect(worstOverspend(cats)).toBe(30)
    expect(worstOverspend([])).toBe(1)
  })

  it('scales the Total column against the totals alone', () => {
    // A year's overrun beside a month's washed every cell out when one scale
    // served both.
    const cats = [
      category('A', [cell('2026-08-01', -30)], { total: total(-600) }),
      category('B', [cell('2026-08-01', -10)], { total: total(-14, false) }),
    ]
    expect(worstTotalOverspend(cats)).toBe(600)
    expect(worstOverspend(cats)).toBe(30)
  })
})

describe('monthTotalTone', () => {
  it('reads a month total by the cent: over, under or on', () => {
    expect(monthTotalTone(monthTotal('2026-08-01', 0, -50))).toBe('over')
    expect(monthTotalTone(monthTotal('2026-08-01', 0, 120))).toBe('under')
    expect(monthTotalTone(monthTotal('2026-08-01', 0, 0.004))).toBe('on')
  })
})

describe('varianceHeadline', () => {
  const money = (n: number) => `$${n.toFixed(2)}`

  it('names an overrun as over plan, by a positive amount', () => {
    expect(varianceHeadline(-120, money)).toEqual({
      label: 'Over plan by',
      value: '$120.00',
      over: true,
    })
  })

  it('names money left in the plan as under plan', () => {
    expect(varianceHeadline(80, money)).toEqual({
      label: 'Under plan by',
      value: '$80.00',
      over: false,
    })
  })

  it('reads exactly on plan as on plan, not as "$0.00" either way', () => {
    expect(varianceHeadline(0, money)).toEqual({
      label: 'Against plan',
      value: 'On plan',
      over: false,
    })
  })

  it('reads float dust as on plan, and a genuine cent as a direction', () => {
    expect(varianceHeadline(0.004, money).value).toBe('On plan')
    expect(varianceHeadline(-0.01, money).label).toBe('Over plan by')
  })
})

describe('totalShareLabel', () => {
  it('says the share, and which way', () => {
    expect(totalShareLabel({ variance_pct: -12.4, over: true })).toBe('12% over')
    expect(totalShareLabel({ variance_pct: 30, over: false })).toBe('30% under')
  })

  it('says "no plan" or "on plan" where there was no plan to take a share of', () => {
    // Budget vs Actual printed "0.0%" for spending nobody planned, which is
    // also what a plan spent to the cent printed.
    expect(totalShareLabel({ variance_pct: null, over: true })).toBe('no plan')
    // A mortgage assigned 1,500 and paid by a 1,500 principal transfer.
    expect(totalShareLabel({ variance_pct: null, over: false })).toBe('on plan')
  })
})

describe('planVsSpentHeadline', () => {
  it('reads chronic, the last complete month, and the category most over', () => {
    const dining = category(
      'Dining Out',
      [cell('2026-07-01', -40), cell('2026-08-01', -60), cell('2026-09-01', -10)],
      { chronic: true }
    )
    const fuel = category('Fuel', [
      cell('2026-07-01', 10),
      cell('2026-08-01', -25),
      cell('2026-09-01', 5),
    ])
    const h = planVsSpentHeadline(report([dining, fuel], [1, 2, 0]))

    expect(h.chronic).toBe(1)
    // August, not September: the running month is not "last month".
    expect(h.lastMonth).toEqual({ month: '2026-08-01', over: 2 })
    expect(h.mostOver).toEqual({ name: 'Dining Out', monthsOver: 3, monthsActive: 3 })
  })

  it("reads the month's count over from the served total, not from the rows on screen", () => {
    // With "Chronic only" ticked the rows are a subset; the headline is the
    // whole report's, as the server counted it.
    const h = planVsSpentHeadline(report([], [0, 7, 0]))
    expect(h.lastMonth).toEqual({ month: '2026-08-01', over: 7 })
  })

  it('has no last month before a month has closed', () => {
    const r = report([])
    r.month_totals = [monthTotal('2026-09-01', 0)]
    expect(planVsSpentHeadline(r).lastMonth).toBeNull()
  })

  it('breaks a tie on months over by the larger overrun', () => {
    const small = category('Small', [cell('2026-07-01', -5), cell('2026-08-01', -5)])
    const big = category('Big', [cell('2026-07-01', -500), cell('2026-08-01', -500)])
    expect(planVsSpentHeadline(report([small, big])).mostOver?.name).toBe('Big')
  })

  it('never names a sinking fund the category most over', () => {
    const premium = category(
      'Home Insurance',
      [cell('2026-07-01', -200), cell('2026-08-01', -200), cell('2026-09-01', -200)],
      { sinking_fund: true }
    )
    const dining = category('Dining Out', [cell('2026-08-01', -20)])
    expect(planVsSpentHeadline(report([premium, dining])).mostOver?.name).toBe('Dining Out')
  })

  it('names nobody when nothing went over', () => {
    const h = planVsSpentHeadline(report([category('Fuel', [cell('2026-08-01', 10)])]))
    expect(h.mostOver).toBeNull()
  })
})

describe('exportRows', () => {
  it('writes the matrix wide, then the Total column', () => {
    const [row] = exportRows([
      category('Groceries', [cell('2026-07-01', -40), cell('2026-08-01', 10)], {
        total: total(-30),
      }),
    ])
    expect(row).toMatchObject({
      category: 'Groceries',
      '2026-07': -40,
      '2026-08': 10,
      total_planned: 300,
      total_spent: 330,
      total_variance: -30,
      months_over: 1,
    })
  })
})
