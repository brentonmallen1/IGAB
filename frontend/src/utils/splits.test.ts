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
import { checkSplit, coverRemainder, fillRemainder, remainderTarget } from './splits'
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

/**
 * "Fill the rest": a split is finished by typing every leg but the last and
 * then doing the subtraction — on a phone, with a keypad that has no minus
 * sign. The remainder already shows; tapping it puts it in the empty leg.
 */
describe('filling the remainder', () => {
  const leg = (amount: string) => ({ amount, categoryId: null })

  it('goes into the first leg with no amount', () => {
    const legs = [leg('60'), leg(''), leg('')]
    expect(remainderTarget(legs, 6000)).toBe(1)
    expect(fillRemainder(legs, 6000).map((l) => l.amount)).toEqual(['60', '60.00', ''])
  })

  it('writes cents the way the editors hold them', () => {
    expect(fillRemainder([leg('10'), leg('')], 1234).map((l) => l.amount)).toEqual(['10', '12.34'])
  })

  it('counts a zero or unreadable leg as empty', () => {
    expect(remainderTarget([leg('0'), leg('5')], 500)).toBe(0)
    expect(remainderTarget([leg('5'), leg('abc')], 500)).toBe(1)
  })

  it('never overwrites a figure a person typed', () => {
    const legs = [leg('60'), leg('20')]
    expect(remainderTarget(legs, 4000)).toBeNull()
    expect(fillRemainder(legs, 4000)).toBe(legs)
  })

  it('has nothing to fill when done or over', () => {
    expect(remainderTarget([leg('')], 0)).toBeNull()
    expect(remainderTarget([leg('')], -500)).toBeNull()
  })

  it('leaves the result a valid split', () => {
    const legs = [
      { amount: '60', categoryId: 'a' },
      { amount: '', categoryId: 'b' },
    ]
    expect(checkSplit(12000, fillRemainder(legs, 6000)).isValid).toBe(true)
  })
})

/**
 * "Cover the rest": the whole remainder into one category, from the phone's
 * split sheet. It is not Fill — Fill needs an empty line already set up;
 * this makes or finds the line itself.
 */
describe('covering the remainder', () => {
  let n = 0
  const newLeg = () => ({ amount: '', categoryId: null as string | null, id: `new${++n}` })
  const leg = (amount: string, categoryId: string | null, id = amount + categoryId) => ({
    amount,
    categoryId,
    id,
  })

  it('adds to the line already in that category, not a second one', () => {
    const legs = [leg('142.18', 'groceries'), leg('38.40', 'household')]
    const out = coverRemainder(legs, 1200, 'groceries', newLeg)
    expect(out.map((l) => [l.categoryId, l.amount])).toEqual([
      ['groceries', '154.18'],
      ['household', '38.40'],
    ])
  })

  it('takes a blank line before adding one', () => {
    const legs = [leg('60', 'groceries'), leg('', null)]
    const out = coverRemainder(legs, 6000, 'kids', newLeg)
    expect(out).toHaveLength(2)
    expect(out[1]).toMatchObject({ categoryId: 'kids', amount: '60.00' })
  })

  it('fills a categorised line that has no amount yet', () => {
    const legs = [leg('60', 'groceries'), leg('', 'kids')]
    expect(coverRemainder(legs, 6000, 'kids', newLeg)[1]).toMatchObject({ amount: '60.00' })
  })

  it('adds a line when none is free', () => {
    const legs = [leg('60', 'groceries'), leg('20', 'household')]
    const out = coverRemainder(legs, 4000, 'kids', newLeg)
    expect(out).toHaveLength(3)
    expect(out[2]).toMatchObject({ categoryId: 'kids', amount: '40.00' })
    expect(out[2].id).toMatch(/^new/)
  })

  it('never touches a line with no category but an amount a person typed', () => {
    const legs = [leg('60', null), leg('20', 'household')]
    const out = coverRemainder(legs, 4000, 'kids', newLeg)
    expect(out[0]).toEqual(legs[0])
    expect(out).toHaveLength(3)
  })

  it('does nothing when the split is done or over', () => {
    const legs = [leg('60', 'groceries')]
    expect(coverRemainder(legs, 0, 'groceries', newLeg)).toBe(legs)
    expect(coverRemainder(legs, -500, 'groceries', newLeg)).toBe(legs)
  })

  it('leaves a valid split', () => {
    const legs = [leg('142.18', 'groceries'), leg('38.40', 'household')]
    const total = 14218 + 3840 + 1200
    const out = coverRemainder(legs, 1200, 'household', newLeg)
    expect(checkSplit(total, out).isValid).toBe(true)
  })
})
