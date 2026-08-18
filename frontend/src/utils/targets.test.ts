/**
 * Mirror-suite for utils/targets — the cases track the backend's
 * TestCalculateStatus (backend/tests/unit/test_target_service.py) so the two
 * implementations cannot drift apart silently, plus the regression that
 * created this module: a savings-balance category whose AVAILABLE met the
 * goal showed a 100% progress bar beside an "Underfunded" pill, because the
 * pill compared ASSIGNED against the target amount for every target type.
 */
import { describe, expect, it } from 'vitest'
import {
  monthsBetween,
  targetMeasuresBalance,
  targetNeededThisMonth,
  targetProgress,
  targetStatus,
} from './targets'

const NOW = new Date('2026-08-18T12:00:00')

function target(target_type: string, target_amount: number, target_date: string | null = null) {
  return { target_type, target_amount, target_date }
}

describe('monthsBetween', () => {
  it('mirrors _months_between', () => {
    expect(monthsBetween(new Date('2024-03-01T00:00:00'), new Date('2024-04-01T00:00:00'))).toBe(1)
    expect(monthsBetween(new Date('2024-01-01T00:00:00'), new Date('2025-01-01T00:00:00'))).toBe(12)
    expect(monthsBetween(new Date('2024-11-01T00:00:00'), new Date('2025-02-01T00:00:00'))).toBe(3)
    // past or same date clamps to 1
    expect(monthsBetween(new Date('2024-05-01T00:00:00'), new Date('2024-03-01T00:00:00'))).toBe(1)
  })
})

describe('targetStatus — monthly/weekly funding measure ASSIGNED', () => {
  it('monthly funded at the full amount', () => {
    expect(targetStatus(target('monthly_funding', 500), 500, 500, NOW)).toBe('funded')
  })

  it('monthly underfunded below it — rollover does not count', () => {
    // available 900 does not matter: "set aside another 500" every month
    expect(targetStatus(target('monthly_funding', 500), 400, 900, NOW)).toBe('underfunded')
  })

  it('overfunded past the 5% grace, funded at exactly 5%', () => {
    expect(targetStatus(target('monthly_funding', 500), 600, 600, NOW)).toBe('overfunded')
    expect(targetStatus(target('monthly_funding', 500), 525, 525, NOW)).toBe('funded')
  })

  it('weekly funding behaves the same', () => {
    expect(targetStatus(target('weekly_funding', 100), 100, 100, NOW)).toBe('funded')
    expect(targetStatus(target('weekly_funding', 100), 50, 50, NOW)).toBe('underfunded')
  })
})

describe('targetStatus — savings balance measures AVAILABLE', () => {
  it('THE regression: balance met with nothing assigned this month is funded', () => {
    expect(targetStatus(target('savings_balance', 1000), 0, 1000, NOW)).toBe('funded')
  })

  it('underfunded while the balance is short', () => {
    expect(targetStatus(target('savings_balance', 1000), 0, 500, NOW)).toBe('underfunded')
  })

  it("funded when this month's assignment covers the shortfall", () => {
    // available=600, shortfall=400, assigned=400 → funded (backend parity)
    expect(targetStatus(target('savings_balance', 1000), 400, 600, NOW)).toBe('funded')
  })
})

describe('targetStatus — needed for spending', () => {
  it('without a date it needs the full amount assigned', () => {
    expect(targetStatus(target('needed_for_spending', 300), 300, 0, NOW)).toBe('funded')
    expect(targetStatus(target('needed_for_spending', 300), 200, 0, NOW)).toBe('underfunded')
  })

  it('with a date it needs the monthly pace, not the whole goal', () => {
    // $1200 by Dec, $0 saved, 4 months out → $300/mo pace
    const t = target('needed_for_spending', 1200, '2026-12-01')
    expect(targetNeededThisMonth(t, 0, NOW)).toBe(300)
    expect(targetStatus(t, 200, 200, NOW)).toBe('underfunded')
    // The pace feeds back on itself (available already contains this month's
    // assignment), so the break-even is assigned = (goal − prior) / (months+1):
    // assign 240 → available 240 → pace (1200−240)/4 = 240 → funded exactly.
    expect(targetNeededThisMonth(t, 240, NOW)).toBe(240)
    expect(targetStatus(t, 240, 240, NOW)).toBe('funded')
    // Assigning the naive pace overshoots the recomputed one — backend parity:
    // assigned 300 → available 300 → pace 225 → past the 5% grace.
    expect(targetStatus(t, 300, 300, NOW)).toBe('overfunded')
  })

  it('existing balance reduces the pace', () => {
    // $1200 by Dec with $600 saved before this month: break-even
    // (1200−600)/(4+1) = 120/mo → available 720 → pace (1200−720)/4 = 120.
    const t = target('needed_for_spending', 1200, '2026-12-01')
    expect(targetNeededThisMonth(t, 720, NOW)).toBe(120)
    expect(targetStatus(t, 120, 720, NOW)).toBe('funded')
    expect(targetStatus(t, 60, 660, NOW)).toBe('underfunded')
  })
})

describe('targetProgress uses the same measure as the status', () => {
  it('savings balance fills by available — bar and pill agree on a met goal', () => {
    const t = target('savings_balance', 1000)
    expect(targetProgress(t, 0, 1000)).toBe(1)
    expect(targetStatus(t, 0, 1000, NOW)).toBe('funded')
    expect(targetProgress(t, 0, 250)).toBe(0.25)
  })

  it('monthly funding fills by assigned', () => {
    const t = target('monthly_funding', 500)
    expect(targetProgress(t, 250, 900)).toBe(0.5)
  })

  it('dated needed-for-spending fills by available (goal progress)', () => {
    const t = target('needed_for_spending', 1200, '2026-12-01')
    expect(targetProgress(t, 0, 600)).toBe(0.5)
  })

  it('clamps to 0..1 and refuses non-positive amounts', () => {
    expect(targetProgress(target('monthly_funding', 500), 800, 800)).toBe(1)
    expect(targetProgress(target('savings_balance', 1000), 0, -50)).toBe(0)
    expect(targetProgress(target('monthly_funding', 0), 100, 100)).toBeNull()
  })
})

describe('targetMeasuresBalance', () => {
  it('is true for savings balance and dated needed-for-spending only', () => {
    expect(targetMeasuresBalance(target('savings_balance', 1))).toBe(true)
    expect(targetMeasuresBalance(target('needed_for_spending', 1, '2026-12-01'))).toBe(true)
    expect(targetMeasuresBalance(target('needed_for_spending', 1))).toBe(false)
    expect(targetMeasuresBalance(target('monthly_funding', 1))).toBe(false)
    expect(targetMeasuresBalance(target('weekly_funding', 1))).toBe(false)
  })
})
