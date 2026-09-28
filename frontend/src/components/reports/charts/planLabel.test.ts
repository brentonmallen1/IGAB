import { describe, expect, it } from 'vitest'
import { planLabel } from './planLabel'

const fmt = (n: number) => `$${n}`

describe('planLabel', () => {
  it('is the plan alone when nothing moved', () => {
    expect(planLabel({ assigned: 500, moved_in: 0, moved_out: 0, plan: 500 }, fmt)).toBe('$500')
  })

  it('names money moved in', () => {
    expect(planLabel({ assigned: 100, moved_in: 2000, moved_out: 0, plan: 2100 }, fmt)).toBe(
      '$2100 (assigned $100 + moved in $2000)'
    )
  })

  it('names money moved out — a brokerage transfer lowers the plan', () => {
    // Neither report could say it: the plan read 200 beside an assignment of
    // 600 with nothing to explain the gap.
    expect(planLabel({ assigned: 600, moved_in: 0, moved_out: 400, plan: 200 }, fmt)).toBe(
      '$200 (assigned $600 − moved out $400)'
    )
  })

  it('names both, and shows the floored plan the server served', () => {
    expect(planLabel({ assigned: 100, moved_in: 300, moved_out: 500, plan: 0 }, fmt)).toBe(
      '$0 (assigned $100 + moved in $300 − moved out $500)'
    )
  })
})
