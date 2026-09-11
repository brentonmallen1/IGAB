import { describe, expect, it } from 'vitest'
import { drillDownFooter } from './drillDownTotals'

const money = (n: number) => `$${n.toFixed(2)}`
const rows = (amounts: number[]) => amounts.map((amount) => ({ amount }))

describe('the total under a drill-down table', () => {
  it('is the sum of the rows it sits under', () => {
    const footer = drillDownFooter(rows([100, 50, 25]), undefined, money)
    expect(footer.shown).toBe(175)
    expect(footer.wider).toBeNull()
    expect(footer.widerLabel).toBeNull()
  })

  it('keeps the wider set beside the rows instead of standing in for them', () => {
    // Budget vs Actual passed the period's whole spend as `total` while
    // "Overspent only" was ticked, and Payee Analysis passed every payee's
    // total beside its top-20 slice — so the row headed Total was larger than
    // the column above it.
    const footer = drillDownFooter(
      rows([400, 300]),
      { total: 1050, count: 5, label: 'payees' },
      money
    )
    expect(footer.shown).toBe(700)
    expect(footer.wider).toBe(1050)
    expect(footer.widerLabel).toBe('of $1050.00 across 5 payees')
    expect(footer.share).toBeCloseTo(66.67, 2)
  })

  it('says nothing extra when the rows ARE the whole set', () => {
    const footer = drillDownFooter(rows([400, 300]), { total: 700, label: 'payees' }, money)
    expect(footer.wider).toBeNull()
  })

  it('treats a rounding cent as the whole set, not as a truncation', () => {
    // Server-rounded per-row figures routinely differ from a server-rounded
    // total by a fraction of a penny; a footnote for that is noise.
    const footer = drillDownFooter(rows([400, 300]), { total: 700.004, label: 'payees' }, money)
    expect(footer.wider).toBeNull()
  })

  it('keeps the sign of a set whose refunds beat its spending', () => {
    // Income vs Expenses lists monthly expenses; a month of net refunds is
    // negative, and abs() turned "we got $40 back" into "we spent $40".
    const footer = drillDownFooter(rows([120, -40]), undefined, money)
    expect(footer.shown).toBe(80)
  })

  it('has no share to state against a zero wider total', () => {
    const footer = drillDownFooter(rows([10]), { total: 0, label: 'payees' }, money)
    expect(footer.share).toBeNull()
  })
})
