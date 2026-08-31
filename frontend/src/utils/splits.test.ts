/**
 * One rule, two languages.
 *
 * The `shared/split_cases.json` block runs the same cases the backend runs in
 * `backend/tests/unit/test_split_predicate.py`. A rule changed on one side
 * only fails on the other, which is the failure this pair exists to catch —
 * there is no shared code path between Python and TypeScript to catch it for
 * us.
 */
import { describe, expect, it } from 'vitest'
import { checkSplit } from './splits'
import { toCents } from './money'
import cases from '../../../shared/split_cases.json'

const leg = (amount: string, categoryId: string | null = 'c1') => ({ amount, categoryId })

describe('agreement with the backend predicate', () => {
  for (const c of cases.cases) {
    it(`${c.total} = [${c.legs.join(' + ')}] → ${c.balances} (${c.note})`, () => {
      const result = checkSplit(
        toCents(c.total),
        c.legs.map((a) => leg(a))
      )
      expect(result.isValid).toBe(c.balances)
    })
  }
})

describe('what makes a split unsavable', () => {
  it('accepts legs that sum exactly', () => {
    const r = checkSplit(1250, [leg('10.00'), leg('2.50')])
    expect(r).toMatchObject({ isValid: true, reason: 'ok', remainingCents: 0 })
  })

  it('reports what is still to assign', () => {
    expect(checkSplit(1250, [leg('10.00')])).toMatchObject({
      isValid: false,
      reason: 'under-assigned',
      remainingCents: 250,
    })
  })

  it('reports going over, with a negative remainder', () => {
    expect(checkSplit(1250, [leg('10.00'), leg('5.00')])).toMatchObject({
      isValid: false,
      reason: 'over-assigned',
      remainingCents: -250,
    })
  })

  it('rejects a leg with no category', () => {
    expect(checkSplit(1250, [leg('10.00'), leg('2.50', null)])).toMatchObject({
      isValid: false,
      reason: 'missing-category',
    })
  })

  it('rejects a zero or negative leg', () => {
    expect(checkSplit(1250, [leg('12.50'), leg('0')]).reason).toBe('non-positive-leg')
    expect(checkSplit(1250, [leg('12.50'), leg('-1')]).reason).toBe('non-positive-leg')
  })

  it('rejects an unparseable leg', () => {
    expect(checkSplit(1250, [leg('abc')]).reason).toBe('non-positive-leg')
  })
})

describe('the clauses that had drifted between the three editors', () => {
  it('requires a positive parent amount', () => {
    // Only the quick-add sheet checked this. The desktop editor's Save button
    // was enabled with an empty amount and wrote a $0.00 transaction.
    expect(checkSplit(0, [])).toMatchObject({ isValid: false, reason: 'no-total' })
    expect(checkSplit(0, [leg('0')])).toMatchObject({ isValid: false, reason: 'no-total' })
    expect(checkSplit(-100, [leg('1.00')])).toMatchObject({ isValid: false, reason: 'no-total' })
  })

  it('requires at least one leg', () => {
    // `splits.every(...)` is true for an empty array, so every editor called
    // "a split with no lines" valid.
    expect(checkSplit(1250, [])).toMatchObject({ isValid: false, reason: 'no-legs' })
  })

  it('sums in integer cents, not floats', () => {
    // 0.10 + 0.20 !== 0.30 in binary floating point.
    expect(checkSplit(30, [leg('0.10'), leg('0.20')]).isValid).toBe(true)
  })

  it('accepts an arithmetic expression as a leg', () => {
    expect(checkSplit(1449, [leg('10.50'), leg('2.50+1.49')]).isValid).toBe(true)
  })
})
