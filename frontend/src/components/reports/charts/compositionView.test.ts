import { describe, expect, it } from 'vitest'
import type { AccountCompositionPoint, AccountCompositionReport } from '../../../types'
import {
  bandLabel,
  compositionBands,
  MANUAL_DEBT_BAND,
  plotted,
  STATED_BAND,
} from './compositionView'

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
    const bands = compositionBands(r, 8)
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
      report([point({ checking: 1000, savings: 0, credit_card: -20 })]),
      8
    )
    expect(bands.map((b) => [b.key, b.colorSlot])).toEqual([
      ['checking', 0],
      ['credit_card', 2],
    ])
  })

  it('the stated and manual bands take the slots after every type', () => {
    const bands = compositionBands(report([point({ checking: 0 }, 9000, -800)]), 8)
    expect(bands.map((b) => [b.key, b.colorSlot])).toEqual([
      [STATED_BAND, 3],
      [MANUAL_DEBT_BAND, 4],
    ])
  })

  it('a type missing from a point reads zero there', () => {
    const bands = compositionBands(report([point({}), point({ checking: 50 })]), 8)
    expect(bands[0].values).toEqual([0, 50])
  })
})

describe('compositionBands past the palette', () => {
  it('a drawn band never shares a colour with another drawn band', () => {
    // Seven types and both bands: nine, on eight slots. The debts band wrapped
    // onto Checking's slot and drew in its colour right beside it.
    const series = [
      'checking',
      'savings',
      'credit_card',
      'mortgage',
      'auto_loan',
      'student_loan',
      'investment',
    ]
    const balances = {
      checking: 1,
      savings: 1,
      credit_card: -1,
      mortgage: -1,
      auto_loan: -1,
      student_loan: 0,
      investment: 1,
    }
    const bands = compositionBands({ points: [point(balances, 5, -5)], series }, 8)
    const slots = bands.map((b) => b.colorSlot)
    expect(new Set(slots).size).toBe(slots.length)
    // Below the palette's size every drawn band keeps its place in the list:
    // the hidden student loan keeps slot 5 free, so the stated band takes 7.
    expect(bands.map((b) => [b.key, b.colorSlot])).toEqual([
      ['checking', 0],
      ['savings', 1],
      ['credit_card', 2],
      ['mortgage', 3],
      ['auto_loan', 4],
      ['investment', 6],
      [STATED_BAND, 7],
      [MANUAL_DEBT_BAND, 5],
    ])
  })
})

describe('bandLabel', () => {
  it('names the two bands and defers to the registry for types', () => {
    expect(bandLabel(STATED_BAND, (k) => k)).toBe('Stated values')
    expect(bandLabel(MANUAL_DEBT_BAND, (k) => k)).toBe('Debts tracked by hand')
    expect(bandLabel('checking', () => 'Checking')).toBe('Checking')
  })
})

describe('plotted', () => {
  const band = (values: number[]) => ({ key: 'k', colorSlot: 0, values })

  it('leaves out the empty months of a band that only sits below the axis', () => {
    const debts = band([0, 0, -8000])
    expect([0, 1, 2].map((i) => plotted(debts, i))).toEqual([null, null, -8000])
  })

  it('keeps a zero in a band above the axis, where it stacks where it belongs', () => {
    const stated = band([0, 300000, 310000])
    expect(plotted(stated, 0)).toBe(0)
  })

  it('keeps a zero in a band that crosses the axis', () => {
    const checking = band([500, 0, -20])
    expect(plotted(checking, 1)).toBe(0)
  })
})
