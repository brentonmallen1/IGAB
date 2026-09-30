import { describe, expect, it } from 'vitest'
import { checkSplit } from '../../../utils/splits'
import { splitLabel, splitProgress, splitStatus } from './splitSummary'

const fmt = (n: number) => `$${n.toFixed(2)}`
const leg = (amount: string, categoryId: string | null = 'c1') => ({ amount, categoryId })

describe('splitStatus', () => {
  it('says what is left, over, or done', () => {
    expect(splitStatus(checkSplit(10000, [leg('60'), leg('28')]), fmt)).toEqual({
      tone: 'short',
      text: '$12.00 left',
    })
    expect(splitStatus(checkSplit(10000, [leg('60'), leg('43')]), fmt)).toEqual({
      tone: 'over',
      text: '$3.00 over',
    })
    expect(splitStatus(checkSplit(10000, [leg('60'), leg('40')]), fmt)).toEqual({
      tone: 'done',
      text: 'Fully split',
    })
  })

  it('names a missing category only once the money adds up', () => {
    expect(splitStatus(checkSplit(10000, [leg('60'), leg('30', null)]), fmt).tone).toBe('short')
    expect(splitStatus(checkSplit(10000, [leg('60'), leg('40', null)]), fmt)).toEqual({
      tone: 'incomplete',
      text: 'Every line needs a category',
    })
  })

  it('asks for the total when there is none', () => {
    expect(splitStatus(checkSplit(0, [leg('60')]), fmt).text).toBe('Enter the total first')
  })
})

describe('splitProgress', () => {
  it('is the share covered, held to 0–100', () => {
    expect(splitProgress(checkSplit(20000, [leg('50'), leg('')]))).toBe(25)
    expect(splitProgress(checkSplit(10000, [leg('150')]))).toBe(100)
    expect(splitProgress(checkSplit(0, [leg('5')]))).toBe(0)
  })
})

describe('splitLabel', () => {
  const names: Record<string, string> = {
    g: 'Groceries',
    h: 'Household',
    p: 'Personal Care',
    k: 'Kids',
  }
  const nameOf = (id: string) => names[id]

  it('lists up to two, then counts the rest', () => {
    expect(splitLabel([{ categoryId: 'g' }, { categoryId: 'h' }], nameOf)).toBe(
      'Groceries, Household'
    )
    expect(
      splitLabel(
        [{ categoryId: 'g' }, { categoryId: 'h' }, { categoryId: 'p' }, { categoryId: 'k' }],
        nameOf
      )
    ).toBe('Groceries, Household, +2')
  })

  it('counts a category once, and says so when none is chosen', () => {
    expect(splitLabel([{ categoryId: 'g' }, { categoryId: 'g' }], nameOf)).toBe('Groceries')
    expect(splitLabel([{ categoryId: null }, { categoryId: null }], nameOf)).toBe(
      '2 lines, no categories yet'
    )
  })
})
