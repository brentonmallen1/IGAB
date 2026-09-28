import { describe, expect, it } from 'vitest'
import type { TrackingEntry } from '../../../types'
import { setAsideStartNote } from './savingsView'

const MONTHS = ['2026-06-01', '2026-07-01', '2026-08-01']
const label = (m: string) => m.slice(0, 7)
const hysa: TrackingEntry = {
  kind: 'account',
  id: 'h',
  name: 'Cascade Point HYSA',
  day: '2026-07-10',
  amount: 1000,
}

describe('setAsideStartNote', () => {
  it('names the account whose linking starts the line', () => {
    expect(setAsideStartNote(MONTHS, [null, 1000, 1020], [[], [hysa], []], label)).toBe(
      'Starts 2026-07, when Cascade Point HYSA was linked.'
    )
  })

  it('several accounts, by count — the key under the chart names them', () => {
    const other = { ...hysa, id: 'b', name: 'Harborstone Savings' }
    expect(setAsideStartNote(MONTHS, [null, 5, 5], [[], [hysa, other], []], label)).toBe(
      'Starts 2026-07, when 2 of its accounts were linked.'
    )
  })

  it('a start with no arrival says it is the first month anything was set aside', () => {
    expect(setAsideStartNote(MONTHS, [null, null, 300], [[], [], []], label)).toBe(
      'Starts 2026-08, the first month anything was set aside.'
    )
  })

  it('no note when the line starts with the window, or never starts', () => {
    expect(setAsideStartNote(MONTHS, [0, 10, 10], [[], [], []], label)).toBeNull()
    expect(setAsideStartNote(MONTHS, [null, null, null], [[], [], []], label)).toBeNull()
  })
})
