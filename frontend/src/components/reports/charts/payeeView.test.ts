import { describe, expect, it } from 'vitest'
import { payeeSubName, recurringRule } from './payeeView'

describe('recurringRule', () => {
  it('states the served threshold, which scales with the range', () => {
    // A fixed "3+ months" was the rule over any range: three scattered months
    // of two years read as a habit.
    expect(recurringRule(6)).toBe('Recurring = seen in 6+ months of the range')
  })

  it('says a short range cannot call anything recurring', () => {
    expect(recurringRule(null)).toBe('Recurring needs a range of 3+ months')
  })
})

describe('payeeSubName', () => {
  it('counts purchases, not split legs', () => {
    expect(payeeSubName({ is_recurring: false, count: 1 })).toBe('1 purchase')
    expect(payeeSubName({ is_recurring: false, count: 4 })).toBe('4 purchases')
  })

  it('names a recurring payee', () => {
    expect(payeeSubName({ is_recurring: true, count: 12 })).toBe('Recurring')
  })
})
