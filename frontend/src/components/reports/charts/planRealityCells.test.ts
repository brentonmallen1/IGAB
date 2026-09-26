import { describe, expect, it } from 'vitest'
import { cellLabel, overspendStyle, planRealityHeadline, worstOverspend } from './planRealityCells'
import { PRIVACY_MASK } from '../../../utils/money'
import type { PlanRealityCategory, PlanRealityCell, PlanRealityReport } from '../../../types'

function cell(month: string, variance: number, over = variance <= -1): PlanRealityCell {
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

function category(
  name: string,
  monthly: PlanRealityCell[],
  extra: Partial<PlanRealityCategory> = {}
): PlanRealityCategory {
  const overs = monthly.filter((m) => m.over)
  return {
    category_id: name,
    category_name: name,
    category_group_name: 'Everyday',
    monthly,
    months_over: overs.length,
    months_active: monthly.length,
    total_assigned: 0,
    total_moved_in: 0,
    total_moved_out: 0,
    total_spent: 0,
    avg_overspend: overs.length ? -overs.reduce((s, m) => s + m.variance, 0) / overs.length : 0,
    chronic: false,
    sinking_fund: false,
    ...extra,
  }
}

const MONTHS = ['2026-07-01', '2026-08-01', '2026-09-01']

function report(categories: PlanRealityCategory[], running = '2026-09-01') {
  return {
    months: MONTHS,
    running_month: running,
    categories,
    total_assigned: 0,
    total_moved_in: 0,
    total_moved_out: 0,
    total_spent: 0,
    chronic_count: categories.filter((c) => c.chronic).length,
  } satisfies PlanRealityReport
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
})

describe('worstOverspend', () => {
  it('scales to the worst over month, ignoring tolerated ones', () => {
    const cats = [category('A', [cell('2026-08-01', -30), cell('2026-09-01', -90, false)])]
    expect(worstOverspend(cats)).toBe(30)
    expect(worstOverspend([])).toBe(1)
  })
})

describe('planRealityHeadline', () => {
  it('reads chronic, last complete month, and the worst category', () => {
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
    const h = planRealityHeadline(report([dining, fuel]))

    expect(h.chronic).toBe(1)
    // August, not September: the running month is not "last month".
    expect(h.lastMonth).toEqual({ month: '2026-08-01', over: 2 })
    expect(h.worst).toEqual({ name: 'Dining Out', monthsOver: 3, monthsActive: 3 })
  })

  it('breaks a tie on months over by the larger overrun', () => {
    const small = category('Small', [cell('2026-07-01', -5), cell('2026-08-01', -5)])
    const big = category('Big', [cell('2026-07-01', -500), cell('2026-08-01', -500)])
    expect(planRealityHeadline(report([small, big])).worst?.name).toBe('Big')
  })

  it('never names a sinking fund the worst', () => {
    const premium = category(
      'Home Insurance',
      [cell('2026-07-01', -200), cell('2026-08-01', -200), cell('2026-09-01', -200)],
      { sinking_fund: true }
    )
    const dining = category('Dining Out', [cell('2026-08-01', -20)])
    expect(planRealityHeadline(report([premium, dining])).worst?.name).toBe('Dining Out')
  })

  it('has no worst when nothing went over', () => {
    const h = planRealityHeadline(report([category('Fuel', [cell('2026-08-01', 10)])]))
    expect(h.worst).toBeNull()
  })
})
