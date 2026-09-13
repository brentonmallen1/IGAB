import { describe, expect, it } from 'vitest'
import type { MoneyShape } from '../api/moneyRules'
import { budgetEffectLines, budgetTermSentence, shapeFor } from './moneyMoves'

const shape = (over: Partial<MoneyShape>): MoneyShape =>
  ({
    key: 'k',
    label: 'l',
    classification: 'asset',
    on_budget: false,
    counts_as_savings: null,
    ...over,
  }) as MoneyShape

describe('shapeFor', () => {
  const shapes = [
    shape({ key: 'cash', on_budget: true }),
    shape({ key: 'saving', counts_as_savings: true }),
    shape({ key: 'keeping', counts_as_savings: false }),
    shape({ key: 'debt', classification: 'liability' }),
  ]

  it('reads the savings flag only where the server says it matters', () => {
    const facts = { classification: 'asset', on_budget: false } as const
    expect(shapeFor(shapes, { ...facts, counts_as_savings: true })?.key).toBe('saving')
    expect(shapeFor(shapes, { ...facts, counts_as_savings: false })?.key).toBe('keeping')
  })

  it('ignores the flag on a shape served with null', () => {
    const debt = { classification: 'liability', on_budget: false } as const
    expect(shapeFor(shapes, { ...debt, counts_as_savings: true })?.key).toBe('debt')
    expect(shapeFor(shapes, { ...debt, counts_as_savings: false })?.key).toBe('debt')
  })
})

describe('budget effect copy', () => {
  const money = (n: number) => `$${n}`

  it('says which way by the sign and never prints a negative', () => {
    expect(budgetTermSentence('ready_to_assign', -1000, money)).toBe(
      'Ready to Assign goes down by $1000'
    )
    expect(budgetTermSentence('card_set_aside', 250, money)).toBe(
      "The card's Ready to pay goes up by $250"
    )
  })

  it('says nothing moves rather than rendering an empty list', () => {
    expect(budgetEffectLines([], money)).toEqual(['No budget figure moves'])
  })
})
