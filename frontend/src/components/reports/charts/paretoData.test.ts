import { describe, expect, it } from 'vitest'
import {
  buildParetoItems,
  cumulativePercents,
  paretoAdherence,
  paretoInsight,
  type ParetoItem,
} from './paretoData'
import pareto from '../../../../../shared/pareto_cases.json'

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

  it('payee mode falls back to summing the visible payees', () => {
    const { sorted, grandTotal, universeCount } = buildParetoItems(
      'payee',
      spending,
      payees,
      undefined
    )
    expect(sorted.map((i) => i.name)).toEqual(['Landlord', 'MegaMart'])
    expect(grandTotal).toBe(850)
    expect(universeCount).toBe(2)
  })

  it('payee mode prefers the served total and count over the ranked rows', () => {
    // The server ranks the top 25 and totals every payee. Summing the ranked
    // rows made concentration a fact about the cap, and disagreed with the
    // `pct` on each row — which is a share of the served total.
    const { grandTotal, universeCount } = buildParetoItems('payee', spending, payees, undefined, {
      total: '4000',
      count: 312,
      itemsTo80: 140,
    })
    expect(grandTotal).toBe(4000)
    expect(universeCount).toBe(312)
  })
})

const items = (totals: number[]): ParetoItem[] =>
  totals.map((total, i) => ({ id: `i${i}`, name: `n${i}`, total, groupKey: null, groupName: null }))

describe('cumulativePercents', () => {
  it('is monotone and ends at 100 when items cover the total', () => {
    const pcts = cumulativePercents(items([50, 30, 20]), 100)
    expect(pcts).toEqual([50, 80, 100])
  })

  it('lies on the axis when there is no positive total to be a share of', () => {
    // `shareOfTotal` has no share to state here; a line still needs a y.
    expect(cumulativePercents(items([1, 2]), 0)).toEqual([0, 0])
    expect(cumulativePercents(items([10, -40]), -30)).toEqual([0, 0])
  })
})

describe('paretoInsight', () => {
  it('finds the item whose cumulative share reaches 80%', () => {
    const { idx80, coverage } = paretoInsight([50, 80, 100], 3)
    expect(idx80).toBe(1)
    // 2 of 3 items produce 80% of spending
    expect(coverage).toBeCloseTo(66.67, 2)
  })

  it('handles the exact-80 boundary inclusively', () => {
    expect(paretoInsight([80, 100], 2).idx80).toBe(0)
  })

  it('returns null coverage when nothing reaches 80%', () => {
    expect(paretoInsight([10, 20], 40)).toEqual({ idx80: -1, coverage: null })
  })

  it('measures coverage against every item, not the ones drawn', () => {
    // The chart draws twenty bars; the array it used to pass was those twenty,
    // so a budget whose 80% point sits at item 34 got `idx80: -1` and no card
    // at all — exactly the diffuse spending the card exists to name.
    const spread = Array.from({ length: 40 }, (_, i) => ((i + 1) / 40) * 100)
    const { idx80, coverage } = paretoInsight(spread, 40)
    expect(idx80).toBe(31)
    expect(coverage).toBeCloseTo(80, 5)

    const drawnOnly = spread.slice(0, 20)
    expect(paretoInsight(drawnOnly, 40).idx80).toBe(-1)
  })
})

describe('paretoAdherence', () => {
  it('measures the threshold on the real coverage, not the rounded label', () => {
    // The card renders `coverage.toFixed(0)`, so 30.4% displays as "30" — and
    // the threshold used to be applied to that string, calling spread-thin
    // spending concentrated on the strength of a rounding step.
    expect(paretoAdherence(30.4, 100)?.adherent).toBe(false)
    expect(paretoAdherence(30, 100)?.adherent).toBe(true)
  })

  it('claims nothing without a coverage figure or with too few items', () => {
    expect(paretoAdherence(null, 100)).toBeNull()
    expect(paretoAdherence(20, 2)).toBeNull()
  })
})

describe('the 80% line, against the cases the backend runs', () => {
  // Category and group modes compute it here; payee mode is served it by
  // `domain/concentration.py`. One fixture holds both to the same answer.
  it.each(pareto.cases)('$note', ({ totals, items_to_80 }) => {
    const sum = totals.reduce((s, t) => s + t, 0)
    const { idx80 } = paretoInsight(cumulativePercents(items(totals), sum), totals.length)
    expect(idx80 === -1 ? null : idx80 + 1).toBe(items_to_80)
  })
})

describe('paretoInsight in payee mode', () => {
  it('draws the card when the ranked top 25 hold under 80% of spending', () => {
    // 312 payees, the top 25 holding $4,120 of $9,850: the cumulative line
    // peaks at 41.8%, so looking for 80% in it found nothing and the card
    // disappeared. The server counted 140 payees to the line.
    const top25 = cumulativePercents(items(Array(25).fill(4120 / 25)), 9850)
    expect(paretoInsight(top25, 312).idx80).toBe(-1)
    const { idx80, coverage } = paretoInsight(top25, 312, 140)
    expect(idx80).toBe(139)
    expect(coverage).toBeCloseTo((140 / 312) * 100, 5)
  })

  it('has no line when nothing was spent', () => {
    expect(paretoInsight([], 0, null)).toEqual({ idx80: -1, coverage: null })
  })
})
