import { describe, expect, it } from 'vitest'
import {
  buildParetoItems,
  cumulativePercents,
  paretoInsight,
  shareOfTotal,
  type ParetoItem,
} from './paretoData'

const spending = [
  { id: 'c1', name: 'Groceries', total: '300', parent_id: 'g1', parent_name: 'Everyday' },
  { id: 'c2', name: 'Gas', total: '100', parent_id: 'g1', parent_name: 'Everyday' },
  { id: 'c3', name: 'Rent', total: '600', parent_id: 'g2', parent_name: 'Home' },
]
const payees = [
  { payee_id: 'p1', payee_name: 'MegaMart', total: '250' },
  { payee_id: 'p2', payee_name: 'Landlord', total: '600' },
]

describe('buildParetoItems', () => {
  it('category mode sorts descending and trusts the backend total', () => {
    const { sorted, grandTotal } = buildParetoItems('category', spending, payees, '1000')
    expect(sorted.map((i) => i.name)).toEqual(['Rent', 'Groceries', 'Gas'])
    expect(sorted[1]).toMatchObject({ groupKey: 'g1', groupName: 'Everyday' })
    expect(grandTotal).toBe(1000)
  })

  it('group mode aggregates category totals per parent group', () => {
    const { sorted, grandTotal } = buildParetoItems('group', spending, payees, '999')
    expect(sorted).toEqual([
      { id: 'g2', name: 'Home', total: 600, groupKey: 'g2', groupName: null },
      { id: 'g1', name: 'Everyday', total: 400, groupKey: 'g1', groupName: null },
    ])
    // group totals are client-summed, not the backend category total
    expect(grandTotal).toBe(1000)
  })

  it('group mode buckets parentless categories as Uncategorized', () => {
    const orphan = [{ id: 'c9', name: 'Misc', total: '50', parent_id: null, parent_name: null }]
    const { sorted } = buildParetoItems('group', orphan, [], '0')
    expect(sorted).toEqual([
      { id: '__none__', name: 'Uncategorized', total: 50, groupKey: '__none__', groupName: null },
    ])
  })

  it('payee mode sums visible payees as the grand total', () => {
    const { sorted, grandTotal } = buildParetoItems('payee', spending, payees, undefined)
    expect(sorted.map((i) => i.name)).toEqual(['Landlord', 'MegaMart'])
    expect(grandTotal).toBe(850)
  })
})

const items = (totals: number[]): ParetoItem[] =>
  totals.map((total, i) => ({ id: `i${i}`, name: `n${i}`, total, groupKey: null, groupName: null }))

describe('cumulativePercents', () => {
  it('is monotone and ends at 100 when items cover the total', () => {
    const pcts = cumulativePercents(items([50, 30, 20]), 100)
    expect(pcts).toEqual([50, 80, 100])
  })

  it('is all zeros when the grand total is zero', () => {
    expect(cumulativePercents(items([1, 2]), 0)).toEqual([0, 0])
  })
})

describe('paretoInsight', () => {
  it('finds the item whose cumulative share reaches 80%', () => {
    const { idx80, pct80coverage } = paretoInsight([50, 80, 100], 3)
    expect(idx80).toBe(1)
    // 2 of 3 items produce 80% of spending
    expect(pct80coverage).toBe('67')
  })

  it('handles the exact-80 boundary inclusively', () => {
    expect(paretoInsight([80, 100], 2).idx80).toBe(0)
  })

  it('returns null coverage when nothing reaches 80%', () => {
    expect(paretoInsight([10, 20], 40)).toEqual({ idx80: -1, pct80coverage: null })
  })
})

describe('shareOfTotal', () => {
  it('is the item share in percent, 0 for a zero denominator', () => {
    expect(shareOfTotal(25, 200)).toBe(12.5)
    expect(shareOfTotal(25, 0)).toBe(0)
  })
})
