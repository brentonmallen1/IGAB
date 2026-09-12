import { describe, expect, it } from 'vitest'
import { availableTone, balancesByCategory } from './categoryBalances'
import { makeCategoryBalance } from '../test-utils/factories'

describe('balancesByCategory', () => {
  it('keys every served balance by its category', () => {
    const groceries = makeCategoryBalance({ category_id: 'c1', available: 240 })
    const salary = makeCategoryBalance({ category_id: 'c9', assigned: null, available: null })
    const map = balancesByCategory({ category_balances: [groceries, salary] })
    expect(map.get('c1')).toBe(groceries)
    // An income row is present with its null, not dropped and not zeroed.
    expect(map.get('c9')?.available).toBeNull()
    expect(map.size).toBe(2)
  })

  it('is empty for a month that has not loaded — never a map of zeros', () => {
    expect(balancesByCategory(undefined).size).toBe(0)
    expect(balancesByCategory(null).get('c1')).toBeUndefined()
  })
})

describe('availableTone', () => {
  const tone = (available: number | null, credit_overspent = 0) =>
    availableTone({ available, credit_overspent })

  it('reads money left as positive and an empty envelope as zero', () => {
    expect(tone(0.01)).toBe('positive')
    expect(tone(0)).toBe('zero')
  })

  it("reads an income category's missing figure as zero, not as red", () => {
    expect(tone(null)).toBe('zero')
  })

  it('reads a cash overspend as the alarm', () => {
    expect(tone(-42)).toBe('negative')
  })

  it('reads red swiped entirely on a card as calm', () => {
    expect(tone(-42, 42)).toBe('negative-on-card')
    expect(tone(-42, 60)).toBe('negative-on-card')
  })

  it('still alarms when only part of the red rode on a card', () => {
    // The cash cent is what charges Ready to Assign.
    expect(tone(-42, 41.99)).toBe('negative')
  })

  it('ignores card spending on an envelope that is not negative', () => {
    expect(tone(10, 25)).toBe('positive')
  })
})
