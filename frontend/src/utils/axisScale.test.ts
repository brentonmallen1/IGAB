import { describe, expect, it } from 'vitest'
import { niceStep, stackedValueAxis, valueAxis } from './axisScale'

describe('niceStep', () => {
  it.each([
    [4125, 5000],
    [1000, 1000],
    [1001, 2000],
    [2100, 2500],
    [0.3, 0.5],
    [7, 10],
  ])('%s → %s', (raw, step) => {
    expect(niceStep(raw)).toBe(step)
  })

  it('never returns a zero or negative step', () => {
    expect(niceStep(0)).toBe(1)
    expect(niceStep(-5)).toBe(1)
    expect(niceStep(Number.NaN)).toBe(1)
  })
})

describe('valueAxis', () => {
  it('gives a tiny negative adjustment a sliver, not a whole step', () => {
    // Income by Source: paycheques up to $16,500 and one −$75 adjustment. The
    // automatic axis ran to −$5,500 — a quarter of the plot below zero.
    const { domain, ticks } = valueAxis([16_500, 9_000, -75])
    expect(domain[1]).toBe(20_000)
    expect(domain[0]).toBeLessThan(-75)
    expect(domain[0]).toBeGreaterThan(-1_000)
    expect(ticks).toEqual([0, 5_000, 10_000, 15_000, 20_000])
  })

  it('rounds a real dip out to whole steps, with ticks below zero', () => {
    const { domain, ticks } = valueAxis([16_000, -3_600])
    expect(domain).toEqual([-5_000, 20_000])
    expect(ticks).toEqual([-5_000, 0, 5_000, 10_000, 15_000, 20_000])
  })

  it('has no negative side when nothing is below zero', () => {
    expect(valueAxis([100, 350]).domain).toEqual([0, 400])
  })

  it('handles an all-negative series', () => {
    const { domain, ticks } = valueAxis([-120, -40])
    expect(domain).toEqual([-150, 0])
    expect(ticks.at(-1)).toBe(0)
  })

  it('draws something for nothing at all', () => {
    const { domain, ticks } = valueAxis([])
    expect(domain[1]).toBeGreaterThan(domain[0])
    expect(ticks[0]).toBe(0)
    expect(valueAxis([0, 0]).domain).toEqual(domain)
  })

  it('keeps float steps tidy', () => {
    expect(valueAxis([0.3]).ticks).toEqual([0, 0.1, 0.2, 0.3])
  })
})

describe('stackedValueAxis', () => {
  it('reads each stack by sign: positives up, negatives down', () => {
    const rows = [
      { month: 'Jul 26', a: 9_000, b: 7_500, c: -75 },
      { month: 'Aug 26', a: 9_000, b: 0, c: 0 },
    ]
    const { domain, ticks } = stackedValueAxis(rows, ['a', 'b', 'c'])
    // 16,500 stacked, not 9,000 — the largest single segment.
    expect(domain[1]).toBe(20_000)
    // The −$75 is a sliver, not a −$5,000 band.
    expect(domain[0]).toBeGreaterThan(-1_000)
    expect(ticks[0]).toBe(0)
  })

  it('ignores the label and any key a row lacks', () => {
    expect(stackedValueAxis([{ month: 'Jul 26', a: 300 }], ['a', 'b']).domain).toEqual([0, 300])
  })
})
