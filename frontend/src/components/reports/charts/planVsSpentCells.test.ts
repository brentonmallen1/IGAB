import { describe, expect, it } from 'vitest'
import {
  balanceLabel,
  coveredAnything,
  envelopeBreakdown,
  exportRows,
  monthOverspent,
  overspendStyle,
  overspentLabel,
  planVsSpentHeadline,
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

/** A month that had 100 and ended at `left`; over when a dollar short. */
function cell(month: string, left: number, over = left <= -1): PlanVsSpentCell {
  return {
    month,
    carried_in: 0,
    assigned: 100,
    moved_in: 0,
    moved_out: 0,
    funded: 100,
    spent: 100 - left,
    other: 0,
    left,
    overspent: Math.max(0, -left),
    over,
    active: true,
    estimated: false,
  }
}

function total(overspent: number, over = overspent >= 1): PlanVsSpentTotal {
  return {
    carried_in: 0,
    assigned: 300,
    moved_in: 0,
    moved_out: 0,
    funded: 300,
    spent: 300 + overspent,
    other: 0,
    left: 0,
    overspent,
    over,
    estimated: false,
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
    avg_overspend: overs.length ? overs.reduce((s, m) => s + m.overspent, 0) / overs.length : 0,
    chronic: false,
    total: total(0),
    ...extra,
  }
}

const MONTHS = ['2026-07-01', '2026-08-01', '2026-09-01']

function monthTotal(month: string, over: number, overspent = 0): PlanVsSpentMonth {
  return {
    month,
    partial_month: month === '2026-09-01',
    carried_in: 0,
    assigned: 0,
    moved_in: 0,
    moved_out: 0,
    funded: 0,
    spent: 0,
    other: 0,
    left: 0,
    overspent,
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
    total_funded: 0,
    total_spent: 0,
    total_other: 0,
    total_left: 0,
    total_overspent: 0,
    chronic_count: categories.filter((c) => c.chronic).length,
    filter_unavailable: false,
  }
}

const money = (n: number) => `$${n.toFixed(0)}`

describe('balanceLabel', () => {
  it('shows what is left unsigned and a shortfall with a minus', () => {
    expect(balanceLabel(-40, false)).toBe('−40')
    expect(balanceLabel(500, false)).toBe('500')
    expect(balanceLabel(4180, false)).toBe('4.2k')
    expect(balanceLabel(0, false)).toBe('0')
  })

  it('never signs a figure that rounds to nothing', () => {
    // A few cents short read "−0", an overspend too small to show, beside a
    // flag that said the month was fine.
    expect(balanceLabel(-0.27, false)).toBe('0')
    expect(balanceLabel(0.3, false)).toBe('0')
    expect(balanceLabel(-0.6, false)).toBe('−1')
  })

  it('is the mask alone in privacy mode, sign and zero included', () => {
    for (const v of [-40, 10, 0, -4180]) expect(balanceLabel(v, true)).toBe(PRIVACY_MASK)
  })
})

describe('overspentLabel', () => {
  it('draws coverage as the shortfall, and nothing covered as a dash', () => {
    expect(overspentLabel(40, false)).toBe('−40')
    expect(overspentLabel(0, false)).toBe('—')
    expect(overspentLabel(0.004, false)).toBe('—')
  })

  it('is the mask alone in privacy mode, a dash included', () => {
    // A dash among masks says which envelopes went negative.
    for (const v of [0, 40]) expect(overspentLabel(v, true)).toBe(PRIVACY_MASK)
  })
})

describe('overspendStyle', () => {
  it('tints only a month the server calls over, deeper for the worst on screen', () => {
    expect(overspendStyle(cell('2026-09-01', 10), 40)).toEqual({})
    expect(overspendStyle(cell('2026-09-01', 0), 40)).toEqual({})
    expect(overspendStyle(cell('2026-09-01', -40), 40).background).toContain('38%')
    expect(overspendStyle(cell('2026-09-01', -20), 40).background).toContain('23%')
  })

  it('mixes into the sunken surface, so a pinned cell stays opaque', () => {
    // Mixed with `transparent`, the months scrolling under a sticky Total
    // showed through its tint.
    expect(overspendStyle(total(90), 90).background).toContain('var(--surface-sunken)')
  })

  it('does not tint a shortfall inside the tolerance', () => {
    // 14 short on a 1,500 mortgage is past a dollar and short of 1%.
    expect(overspendStyle(cell('2026-09-01', -14, false), 40)).toEqual({})
  })

  it('tints a Total by its own verdict', () => {
    expect(overspendStyle(total(90), 90).background).toContain('38%')
    expect(overspendStyle(total(14, false), 90)).toEqual({})
  })
})

describe('worstOverspend', () => {
  it('scales to the worst over month, ignoring tolerated ones', () => {
    const cats = [category('A', [cell('2026-08-01', -30), cell('2026-09-01', -90, false)])]
    expect(worstOverspend(cats)).toBe(30)
    expect(worstOverspend([])).toBe(1)
  })

  it('scales the Total column against the totals alone', () => {
    const cats = [
      category('A', [cell('2026-08-01', -30)], { total: total(600) }),
      category('B', [cell('2026-08-01', -10)], { total: total(14, false) }),
    ]
    expect(worstTotalOverspend(cats)).toBe(600)
    expect(worstOverspend(cats)).toBe(30)
  })
})

describe('monthOverspent', () => {
  it('reads the served count of categories over', () => {
    expect(monthOverspent(monthTotal('2026-08-01', 2, 80))).toBe(true)
    expect(monthOverspent(monthTotal('2026-08-01', 0, 0.3))).toBe(false)
  })

  it('never calls the running month overspent', () => {
    expect(monthOverspent(monthTotal('2026-09-01', 3, 80))).toBe(false)
  })
})

describe('coveredAnything', () => {
  it('reads by the cent, so float dust is nothing', () => {
    expect(coveredAnything(0.004)).toBe(false)
    expect(coveredAnything(0.01)).toBe(true)
  })
})

describe('envelopeBreakdown', () => {
  it('says what it started with, what it spent and what was left', () => {
    // case E, March: nothing assigned, living off January's 600.
    const c = { ...cell('2026-03-01', 300), carried_in: 400, assigned: 0, spent: 100, funded: 400 }
    expect(envelopeBreakdown(c, money)).toBe('carried in $400 · spent $100 · left $300')
  })

  it('names money moved in and out', () => {
    const c = { ...cell('2026-03-01', 0), carried_in: 1000, assigned: 0, moved_out: 1000, spent: 0 }
    expect(envelopeBreakdown(c, money)).toBe(
      'carried in $1000 · moved out $1000 · spent $0 · left $0'
    )
  })

  it('says so where the carry in is unknown', () => {
    expect(envelopeBreakdown({ ...cell('2026-03-01', 0), carried_in: null }, money)).toMatch(
      /^carryover unknown · /
    )
  })

  it('names what the budget page counts that the ledger does not', () => {
    const c = { ...cell('2026-03-01', 30), other: -40 }
    expect(envelopeBreakdown(c, money)).toContain('other $-40 (pending')
  })

  it("closes a span's sum with what Ready to Assign covered", () => {
    expect(envelopeBreakdown(total(80), money, { span: true })).toBe(
      'carried in $0 · assigned $300 · spent $380 · Ready to Assign covered $80 · left $0'
    )
    // A month states its own negative left instead.
    expect(envelopeBreakdown(total(80), money)).not.toContain('covered')
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
    const h = planVsSpentHeadline(report([], [0, 7, 0]))
    expect(h.lastMonth).toEqual({ month: '2026-08-01', over: 7 })
  })

  it('has no last month before a month has closed', () => {
    const r = report([])
    r.month_totals = [monthTotal('2026-09-01', 0)]
    expect(planVsSpentHeadline(r).lastMonth).toBeNull()
  })

  it('breaks a tie on months over by the larger coverage', () => {
    const small = category('Small', [cell('2026-07-01', -5), cell('2026-08-01', -5)])
    const big = category('Big', [cell('2026-07-01', -500), cell('2026-08-01', -500)])
    expect(planVsSpentHeadline(report([small, big])).mostOver?.name).toBe('Big')
  })

  it('names nobody when nothing went over', () => {
    const h = planVsSpentHeadline(report([category('Fuel', [cell('2026-08-01', 10)])]))
    expect(h.mostOver).toBeNull()
  })
})

describe('exportRows', () => {
  it('writes what was left each month wide, then the Total column', () => {
    const [row] = exportRows([
      category('Groceries', [cell('2026-07-01', -40), cell('2026-08-01', 10)], {
        total: total(30),
      }),
    ])
    expect(row).toMatchObject({
      category: 'Groceries',
      '2026-07': -40,
      '2026-08': 10,
      total_funded: 300,
      total_spent: 330,
      total_overspent: 30,
      left: 0,
      months_over: 1,
    })
  })
})
