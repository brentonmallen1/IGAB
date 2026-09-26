import { describe, expect, it } from 'vitest'
import type { AccountCompositionPoint, AccountCompositionReport } from '../../../types'
import { bandLabel, compositionBands, MANUAL_DEBT_BAND, STATED_BAND } from './compositionView'

const point = (
  balances: Record<string, number>,
  stated = 0,
  manual = 0
): AccountCompositionPoint => ({
  date: '2026-09-01',
  balances,
  stated_assets: stated,
  manual_debts: manual,
  net_worth: Object.values(balances).reduce((a, b) => a + b, 0) + stated + manual,
  asset_value_total: stated,
  entered: 0,
  entries: [],
})

const report = (points: AccountCompositionPoint[]): AccountCompositionReport => ({
  points,
  series: ['checking', 'savings', 'credit_card'],
})

describe('compositionBands', () => {
  it('stacks every band so it sums to Net, with the two no account holds', () => {
    const r = report([point({ checking: 1000, savings: 5000, credit_card: -2000 }, 300000, -50000)])
    const bands = compositionBands(r)
    expect(bands.map((b) => b.key)).toEqual([
      'checking',
      'savings',
      'credit_card',
      STATED_BAND,
      MANUAL_DEBT_BAND,
    ])
    const stack = bands.reduce((sum, b) => sum + b.values[0], 0)
    expect(stack).toBe(r.points[0].net_worth)
  })

  it('a band zero across the window is not drawn, and keeps its colour slot', () => {
    // The savings account held nothing in this range: checking keeps slot 0
    // and the card keeps slot 2, as on every other range.
    const bands = compositionBands(
      report([point({ checking: 1000, savings: 0, credit_card: -20 })])
    )
    expect(bands.map((b) => [b.key, b.colorSlot])).toEqual([
      ['checking', 0],
      ['credit_card', 2],
    ])
  })

  it('the stated and manual bands take the slots after every type', () => {
    const bands = compositionBands(report([point({ checking: 0 }, 9000, -800)]))
    expect(bands.map((b) => [b.key, b.colorSlot])).toEqual([
      [STATED_BAND, 3],
      [MANUAL_DEBT_BAND, 4],
    ])
  })

  it('a type missing from a point reads zero there', () => {
    const bands = compositionBands(report([point({}), point({ checking: 50 })]))
    expect(bands[0].values).toEqual([0, 50])
  })
})

describe('bandLabel', () => {
  it('names the two bands and defers to the registry for types', () => {
    expect(bandLabel(STATED_BAND, (k) => k)).toBe('Stated values')
    expect(bandLabel(MANUAL_DEBT_BAND, (k) => k)).toBe('Debts tracked by hand')
    expect(bandLabel('checking', () => 'Checking')).toBe('Checking')
  })
})
