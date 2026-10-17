import { describe, expect, it } from 'vitest'
import { availableTone, balancesByCategory, withAssignments } from './categoryBalances'
import { makeCategoryBalance } from '../test-utils/factories'
import type { BudgetMonth } from '../types'

describe('withAssignments', () => {
  const month = (
    balances = [
      makeCategoryBalance({ category_id: 'rent', assigned: 900, activity: -900, available: 0 }),
      makeCategoryBalance({ category_id: 'food', assigned: 300, activity: -340, available: -40 }),
    ]
  ) =>
    ({
      month: '2026-07-01',
      to_be_assigned: 500,
      total_assigned: 1200,
      category_balances: balances,
    }) as unknown as BudgetMonth

  it('moves Available with Assigned and Ready to Assign against both', () => {
    const next = withAssignments(month(), '2026-07-01', new Map([['food', 380]]))
    const food = balancesByCategory(next).get('food')!
    expect(food.assigned).toBe(380)
    expect(food.available).toBe(40) // was 40 red; 80 more assigned
    expect(next.to_be_assigned).toBe(420)
    expect(next.total_assigned).toBe(1280)
  })

  it('sums several envelopes, up and down, into one Ready to Assign change', () => {
    // The inspector's buttons set many at once: rent down 100, food up 50.
    const next = withAssignments(
      month(),
      '2026-07-01',
      new Map([
        ['rent', 800],
        ['food', 350],
      ])
    )
    expect(next.to_be_assigned).toBe(550)
    expect(balancesByCategory(next).get('rent')!.available).toBe(-100)
  })

  it('adds a row for an envelope with none, claiming nothing the server decides', () => {
    const next = withAssignments(month([]), '2026-07-01', new Map([['gifts', 25]]))
    const gifts = balancesByCategory(next).get('gifts')!
    expect(gifts).toMatchObject({ assigned: 25, available: 25, activity: 0 })
    expect(gifts.target_status).toBeNull()
    expect(gifts.credit_overspent).toBe(0)
    expect(next.to_be_assigned).toBe(475)
  })

  it('leaves every envelope it was not given alone, and the input untouched', () => {
    const before = month()
    const next = withAssignments(before, '2026-07-01', new Map([['food', 0]]))
    expect(balancesByCategory(next).get('rent')).toBe(balancesByCategory(before).get('rent'))
    expect(balancesByCategory(before).get('food')!.assigned).toBe(300)
  })

  it('changes nothing for no amounts', () => {
    const next = withAssignments(month(), '2026-07-01', new Map())
    expect(next.to_be_assigned).toBe(500)
    expect(next.category_balances).toHaveLength(2)
  })
})

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
