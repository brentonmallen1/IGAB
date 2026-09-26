import { describe, expect, it } from 'vitest'
import { staleNote, statedNote } from './netWorthView'

const money = (n: number) => `$${n.toLocaleString('en-US')}`
const day = (d: string) => `<${d}>`

const HOUSE = {
  kind: 'stated_asset' as const,
  id: 'h',
  name: 'Maple St House',
  value: 310000,
  as_of: '2026-09-02',
}
const LOAN = {
  kind: 'manual_debt' as const,
  id: 'l',
  name: 'Jane Doe IOU',
  value: 800,
  as_of: null,
}

describe('statedNote', () => {
  it('names each stated value with the day it was true', () => {
    expect(statedNote([HOUSE, LOAN], 'stated_asset', money, day)).toBe(
      'Assets include $310,000 of stated value, with no account behind it — Maple St House as of <2026-09-02>.'
    )
  })

  it('a debt with no dated balance says so', () => {
    expect(statedNote([HOUSE, LOAN], 'manual_debt', money, day)).toBe(
      'Liabilities include $800 of debt tracked by hand, with no account behind it — Jane Doe IOU (no date recorded).'
    )
  })

  it('totals several of a kind and lists each', () => {
    const car = { ...HOUSE, id: 'c', name: 'Cedar Wagon', value: 9000, as_of: '2026-07-01' }
    expect(statedNote([HOUSE, car], 'stated_asset', money, day)).toContain(
      '$319,000 of stated value, with no account behind it — Maple St House as of <2026-09-02>; Cedar Wagon as of <2026-07-01>.'
    )
  })

  it('none of a kind is no note', () => {
    expect(statedNote([HOUSE], 'manual_debt', money, day)).toBeNull()
  })
})

describe('staleNote', () => {
  it('lists each flat line with when it last moved', () => {
    expect(
      staleNote(
        [
          { kind: 'manual_debt', id: 'l', name: 'Jane Doe IOU', last_changed: null },
          {
            kind: 'account',
            id: 'a',
            name: 'Harborstone Checking',
            last_changed: '2026-07-10',
          },
        ],
        60,
        day
      )
    ).toBe(
      'Unchanged for 60+ days, so flat on the chart because nothing updated them: Jane Doe IOU (no date recorded), Harborstone Checking (last moved <2026-07-10>).'
    )
  })

  it('one reads as it', () => {
    expect(
      staleNote(
        [{ kind: 'account', id: 'a', name: 'Harborstone Checking', last_changed: '2026-07-10' }],
        60,
        day
      )
    ).toContain('nothing updated it:')
  })

  it('none is no note', () => {
    expect(staleNote([], 60, day)).toBeNull()
  })
})
