import { describe, expect, it } from 'vitest'
import type { CashProjectionPoint } from '../../../types'
import { ifIncomeStopped } from '../../../test-utils/runwayFixtures'
import {
  PROJECTION_BANDS,
  STOPPED_LABEL,
  chosenStoppedOption,
  moneyAvailable,
  projectionRows,
  projectionTooltipEntries,
  projectionWarning,
  spendingAvailable,
} from './cashProjectionView'

const point = (date: string, p10: number, p50: number, p90: number): CashProjectionPoint => ({
  date,
  p10,
  p25: (p10 + p50) / 2,
  p50,
  p75: (p50 + p90) / 2,
  p90,
})

describe('projectionRows', () => {
  it('carries each band as its own [low, high] range', () => {
    const [row] = projectionRows([point('2026-10-01', -400, 600, 1800)], (d) => `L${d}`)
    expect(row.outer).toEqual([-400, 1800])
    expect(row.inner).toEqual([100, 1200])
    expect(row.date).toBe('L2026-10-01')
    expect(row.fullDate).toBe('2026-10-01')
  })

  it('keeps a low band below zero as drawn data, not a stacked difference', () => {
    // The stacked chart drew p90 on top of an opaque p10 "eraser": the
    // shading ran from 0 to p90, and a p10 of -400 was never plotted — the
    // axis was sized by the stack and could not reach it. A range keeps the
    // real low, so the axis domain includes it.
    const rows = projectionRows(
      [point('2026-10-01', 200, 900, 1500), point('2026-10-02', -400, 600, 1800)],
      (d) => d
    )
    const lows = rows.flatMap((r) => [r.outer[0], r.inner[0]])
    const highs = rows.flatMap((r) => [r.outer[1], r.inner[1]])
    expect(Math.min(...lows)).toBe(-400)
    expect(Math.max(...highs)).toBe(1800)
    for (const r of rows) {
      expect(r.outer[0]).toBeLessThanOrEqual(r.inner[0])
      expect(r.inner[1]).toBeLessThanOrEqual(r.outer[1])
    }
  })

  it('is empty for no points', () => {
    expect(projectionRows([], (d) => d)).toEqual([])
  })

  it('places the If income stopped line on its served days only', () => {
    // Two served points, joined straight by the chart: the balance between
    // them is drawn, not stated, so no row in between carries one.
    const points = ['2026-09-26', '2026-09-27', '2026-09-28'].map((d) => point(d, 0, 500, 900))
    const rows = projectionRows(points, (d) => d, [
      { date: '2026-09-26', balance: 20000 },
      { date: '2026-09-28', balance: 19934.3 },
    ])
    expect(rows.map((r) => r.stopped)).toEqual([20000, undefined, 19934.3])
    expect('stopped' in rows[1]).toBe(false)
  })

  it('draws no line with no served points', () => {
    const rows = projectionRows([point('2026-09-26', 0, 500, 900)], (d) => d)
    expect(rows[0].stopped).toBeUndefined()
  })
})

describe('PROJECTION_BANDS', () => {
  it('names two bands, one per swatch, in one vocabulary', () => {
    // The key said "Likely range (10–90%)" with one swatch while the info
    // panel called 25–75 "likely" and 10–90 "most scenarios".
    expect(PROJECTION_BANDS.inner.label).toBe('Middle half (25–75%)')
    expect(PROJECTION_BANDS.outer.label).toBe('8 in 10 (10–90%)')
  })

  it('shows the inner swatch as the chart does: its layer over the outer one', () => {
    const { inner, outer } = PROJECTION_BANDS
    expect(outer.swatchOpacity).toBe(outer.fillOpacity)
    expect(inner.swatchOpacity).toBeCloseTo(1 - (1 - outer.fillOpacity) * (1 - inner.fillOpacity))
    expect(inner.swatchOpacity).toBeGreaterThan(outer.swatchOpacity)
  })
})

describe('projectionTooltipEntries', () => {
  it('reads every band edge in words, highest first', () => {
    const [row] = projectionRows([point('2026-10-01', -400, 600, 1800)], (d) => d)
    expect(projectionTooltipEntries(row).map((e) => [e.name, e.value])).toEqual([
      ['1 in 10 high', 1800],
      ['1 in 4 high', 1200],
      ['Median', 600],
      ['1 in 4 low', 100],
      ['1 in 10 low', -400],
    ])
  })

  it('adds the If income stopped balance on a day the server stated one', () => {
    const [row] = projectionRows([point('2026-10-01', -400, 600, 1800)], (d) => d, [
      { date: '2026-10-01', balance: 12000 },
    ])
    expect(projectionTooltipEntries(row).at(-1)).toEqual({
      name: STOPPED_LABEL,
      value: 12000,
      color: 'var(--text-muted)',
    })
  })

  it('never names the retired Scheduled only line', () => {
    const [row] = projectionRows([point('2026-10-01', -400, 600, 1800)], (d) => d)
    expect(projectionTooltipEntries(row).map((e) => e.name)).not.toContain('Scheduled only')
  })
})

describe('chosenStoppedOption', () => {
  it('opens on the served default — the Overview’s runway — until someone picks', () => {
    const option = chosenStoppedOption(ifIncomeStopped(), null, null)
    expect([option?.spending, option?.money]).toEqual(['essentials', 'with_fund'])
  })

  it('draws the remembered choice', () => {
    const option = chosenStoppedOption(ifIncomeStopped(), 'all', 'with_savings')
    expect([option?.spending, option?.money]).toEqual(['all', 'with_savings'])
    expect(option?.months).toBe(6.3)
  })

  it('falls back to the default money when the remembered fund was un-chosen', () => {
    const option = chosenStoppedOption(ifIncomeStopped({ noFund: true }), 'essentials', 'with_fund')
    expect([option?.spending, option?.money]).toEqual(['essentials', 'checking'])
  })

  it('falls back to all spending when the remembered tier lost its tags', () => {
    const option = chosenStoppedOption(ifIncomeStopped({ untagged: true }), 'essentials', null)
    expect([option?.spending, option?.money]).toEqual(['all', 'with_fund'])
  })
})

describe('picker availability', () => {
  it('offers everything on a budget with tags and a fund', () => {
    const stopped = ifIncomeStopped()
    expect(spendingAvailable(stopped, 'essentials')).toBe(true)
    expect(moneyAvailable(stopped, 'with_fund')).toBe(true)
  })

  it('disables + Emergency fund when no fund is chosen, and nothing else', () => {
    const stopped = ifIncomeStopped({ noFund: true })
    expect(moneyAvailable(stopped, 'with_fund')).toBe(false)
    expect(moneyAvailable(stopped, 'checking')).toBe(true)
    expect(moneyAvailable(stopped, 'with_savings')).toBe(true)
  })

  it('disables the tiers nothing is tagged into, never All', () => {
    const stopped = ifIncomeStopped({ untagged: true })
    expect(spendingAvailable(stopped, 'all')).toBe(true)
    expect(spendingAvailable(stopped, 'cost_of_living')).toBe(false)
    expect(spendingAvailable(stopped, 'essentials')).toBe(false)
  })
})

describe('projectionWarning', () => {
  it('says nothing when neither band crosses', () => {
    expect(projectionWarning({ goes_negative_date: null, p10_negative_date: null })).toBeNull()
    expect(projectionWarning(undefined)).toBeNull()
  })

  it('gives the soft line when only the 1 in 10 low band crosses', () => {
    // The old banner read the median alone, which brushed zero on some
    // days' seeds and not others: the warning came and went with the seed.
    expect(
      projectionWarning({ goes_negative_date: null, p10_negative_date: '2026-11-03' })
    ).toEqual({
      kind: 'possible',
      date: '2026-11-03',
      lead: 'About a 1 in 10 chance of dipping below',
    })
  })

  it('gives the stronger line, on the median’s date, when the median crosses', () => {
    expect(
      projectionWarning({ goes_negative_date: '2026-12-01', p10_negative_date: '2026-11-03' })
    ).toEqual({
      kind: 'likely',
      date: '2026-12-01',
      lead: 'More likely than not to be below',
    })
  })
})
