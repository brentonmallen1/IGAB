import { describe, expect, it } from 'vitest'
import type { EmergencyFund } from '../../types'
import { formatMoney } from '../../utils/money'
import { countingLine, countingParts } from './countingLine'

const NOTHING: EmergencyFund = {
  set_up: false,
  total: null,
  categories: [],
  accounts: [],
  external: { declared: false, amount: null, as_of: null, note: null },
}

const FULL: EmergencyFund = {
  set_up: true,
  total: 9400,
  categories: [{ id: 'c1', name: 'Emergency Fund', balance: 2400 }],
  accounts: [{ id: 'a1', name: 'Harborstone Reserve', balance: 6000 }],
  external: { declared: true, amount: 1000, as_of: '2026-09-01', note: null },
}

const money = (n: number) => formatMoney(n)

describe('countingLine', () => {
  it('names every part in served order, with its balance', () => {
    expect(countingLine(FULL, money)).toBe(
      'Emergency Fund envelope $2,400.00 · Harborstone Reserve $6,000.00 · kept elsewhere $1,000.00'
    )
  })

  it('is null when nothing is set up', () => {
    expect(countingLine(NOTHING, money)).toBeNull()
    expect(countingParts(NOTHING, money)).toEqual([])
  })

  it('says a declaration without a figure, never $0', () => {
    const covered: EmergencyFund = {
      ...NOTHING,
      set_up: true,
      external: { declared: true, amount: null, as_of: '2026-09-01', note: null },
    }
    expect(countingLine(covered, money)).toBe('some kept elsewhere')
  })

  it('formats through the formatter it is given, so privacy masks apply', () => {
    expect(countingLine(FULL, () => '$••••')).toBe(
      'Emergency Fund envelope $•••• · Harborstone Reserve $•••• · kept elsewhere $••••'
    )
  })
})
