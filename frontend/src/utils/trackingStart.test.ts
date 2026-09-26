import { describe, expect, it } from 'vitest'
import type { TrackingEntry } from '../types'
import {
  arrivalLine,
  arrivalMarks,
  arrivalSummary,
  firstFigure,
  likeForLikeLine,
  namedArrivals,
  signedMoney,
} from './trackingStart'

const fmt = (n: number) =>
  `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

const entry = (
  name: string,
  amount: number,
  kind: TrackingEntry['kind'] = 'account'
): TrackingEntry => ({ kind, id: name, name, day: '2026-07-05', amount })

describe('arrivalSummary', () => {
  it('counts each kind and signs the total', () => {
    expect(
      arrivalSummary([entry('Cascade Point Brokerage', 20000), entry('Sapphire Visa', -2300)], fmt)
    ).toBe('2 accounts added: +$17,700')
  })

  it('names history from before a budget start apart from an arrival', () => {
    // A card linked in June with history to September was "added" four times.
    expect(
      arrivalSummary(
        [entry('Sapphire Visa', -150, 'pre_start'), entry('Harborstone Card', -50, 'pre_start')],
        fmt
      )
    ).toBe('History from before budget start on 2 accounts: −$200')
    expect(
      arrivalSummary(
        [entry('Cascade Point HYSA', 1000), entry('Sapphire Visa', -150, 'pre_start')],
        fmt
      )
    ).toBe('1 account added · history from before budget start on 1 account: +$850')
  })

  it('names stated values and manual debts in their own words, accounts first', () => {
    expect(
      arrivalSummary(
        [
          entry('Harborstone Family Loan', -50000, 'manual_debt'),
          entry('Maple St House', 300000, 'stated_asset'),
          entry('Cascade Point HYSA', 1000),
        ],
        fmt
      )
    ).toBe('1 account added · 1 value first stated · 1 debt first recorded: +$251,000')
  })

  it('a debt arriving reads as a minus', () => {
    expect(arrivalSummary([entry('Sapphire Visa', -2300)], fmt)).toBe('1 account added: −$2,300')
  })
})

describe('signedMoney and arrivalLine', () => {
  it('always carries a sign, except on zero', () => {
    expect(signedMoney(5, fmt)).toBe('+$5')
    expect(signedMoney(-5, fmt)).toBe('−$5')
    expect(signedMoney(0, fmt)).toBe('$0')
    expect(arrivalLine(entry('Maple St House', 300000, 'stated_asset'), fmt)).toBe(
      'Maple St House +$300,000'
    )
  })
})

describe('arrivalMarks', () => {
  it('numbers the points that carry arrivals, in chart order', () => {
    const marks = arrivalMarks(
      [
        { date: '2026-06-01', entries: [] },
        { date: '2026-07-01', entries: [entry('Cascade Point Brokerage', 20000)] },
        { date: '2026-08-01', entries: [] },
        {
          date: '2026-09-01',
          entries: [entry('Maple St House', 300000, 'stated_asset')],
        },
      ],
      fmt
    )
    expect(marks.map((m) => [m.index, m.label, m.summary])).toEqual([
      [1, '1', '1 account added: +$20,000'],
      [3, '2', '1 value first stated: +$300,000'],
    ])
  })

  it('none on a chart where nothing arrived', () => {
    expect(arrivalMarks([{ date: '2026-06-01', entries: [] }], fmt)).toEqual([])
  })
})

describe('likeForLikeLine', () => {
  it('names what the headline leaves out', () => {
    expect(likeForLikeLine(-3400, 624000, 620600, fmt)).toEqual({
      value: '−$3,400',
      sub: '+$620,600 on the chart · +$624,000 of it from tracking starting',
    })
  })

  it('says when nothing was left out', () => {
    expect(likeForLikeLine(1200, 0, 1200, fmt)?.sub).toBe(
      'Nothing began being counted in this range'
    )
  })

  it('no change to state is no line', () => {
    expect(likeForLikeLine(null, 0, 0, fmt)).toBeNull()
  })
})

describe('firstFigure', () => {
  it('the first month with a figure, a zero included', () => {
    expect(firstFigure([null, null, 0, 5])).toBe(2)
    expect(firstFigure([null, null])).toBeNull()
    expect(firstFigure([])).toBeNull()
  })
})

describe('namedArrivals', () => {
  it('names up to six, then counts the rest', () => {
    const many = Array.from({ length: 8 }, (_, i) => entry(`Account ${i + 1}`, 100 - i))
    expect(namedArrivals(many, fmt)).toBe(
      'Account 1 +$100 · Account 2 +$99 · Account 3 +$98 · Account 4 +$97 · Account 5 +$96 · Account 6 +$95 · and 2 more'
    )
  })

  it('names all of a short list', () => {
    expect(namedArrivals([entry('Cascade Point HYSA', 1000)], fmt)).toBe(
      'Cascade Point HYSA +$1,000'
    )
  })
})
