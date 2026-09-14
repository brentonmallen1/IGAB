import { describe, expect, it } from 'vitest'
import {
  AT_MEANS_BAND_PCT,
  marginPhrase,
  meansLine,
  meansReading,
  meansTrend,
  netPhrase,
  outflowSharePhrase,
  type MeansMargin,
} from './livingMeans'

describe('meansReading', () => {
  it('holds the band the dialog prints', () => {
    // The copy quotes this constant; a change to it has to be a decision.
    expect(AT_MEANS_BAND_PCT).toBe(5)
  })

  describe('with no income to measure against', () => {
    it('is unknown with nothing in and nothing out', () => {
      const r = meansReading(0, 0)
      expect(r.standing).toBe('unknown')
      expect(r.band).toBeNull()
      expect(r.margin).toBeNull()
      expect(r.net).toBe(0)
      expect(r.note).toMatch(/no income was recorded/i)
    })

    it('is unknown, not above, when money went out and none came in', () => {
      const r = meansReading(0, 1200)
      expect(r.standing).toBe('unknown')
      expect(r.short).toBe('—')
      // Still a fact worth stating: the period ran 1,200 short.
      expect(r.net).toBe(-1200)
    })

    it('is unknown when clawbacks beat income, and says why', () => {
      // A refund-heavy month: 400 of pay less 650 reversed.
      const r = meansReading(-250, 300)
      expect(r.standing).toBe('unknown')
      expect(r.band).toBeNull()
      expect(r.note).toMatch(/nets below zero/i)
      expect(r.net).toBe(-550)
    })

    it('is unknown below a cent of income', () => {
      expect(meansReading(0.004, 0).standing).toBe('unknown')
    })
  })

  describe('below your means', () => {
    it('reads nothing going out as below, with all of it left over', () => {
      const r = meansReading(4000, 0)
      expect(r.standing).toBe('below')
      expect(r.label).toBe('Living below your means')
      expect(r.net).toBe(4000)
      expect(r.margin).toEqual({ pct: 100, direction: 'under' })
    })

    it('reads net refunds on the outflow side as below', () => {
      const r = meansReading(1000, -50)
      expect(r.standing).toBe('below')
      expect(r.net).toBe(1050)
    })

    it('states the net and the share of income', () => {
      const r = meansReading(5000, 4000)
      expect(r.standing).toBe('below')
      expect(r.net).toBe(1000)
      expect(r.margin).toEqual({ pct: 20, direction: 'under' })
    })
  })

  describe('the band edges, on 5,000 of income (band 4,750 to 5,250)', () => {
    it('states the band', () => {
      expect(meansReading(5000, 5000).band).toEqual({ low: 4750, high: 5250 })
    })

    it('reads the lower edge as at and a cent under it as below', () => {
      expect(meansReading(5000, 4750).standing).toBe('at')
      expect(meansReading(5000, 4749.99).standing).toBe('below')
    })

    it('reads the upper edge as at and a cent over it as above', () => {
      expect(meansReading(5000, 5250).standing).toBe('at')
      expect(meansReading(5000, 5250.01).standing).toBe('above')
    })

    it('reads breaking even as at', () => {
      const r = meansReading(5000, 5000)
      expect(r.standing).toBe('at')
      expect(r.net).toBe(0)
      expect(r.note).toContain('5%')
    })

    it('reads above with the shortfall as a negative net', () => {
      const r = meansReading(5000, 6000)
      expect(r.standing).toBe('above')
      expect(r.label).toBe('Living above your means')
      expect(r.net).toBe(-1000)
      expect(r.margin).toEqual({ pct: 20, direction: 'over' })
    })
  })

  describe('rounding', () => {
    it('floors the band to whole cents so the printed edge is inside it', () => {
      // 5% of 100.10 is 5.005: the band is 95.10 to 105.10 — not 105.11,
      // which a rounded display of 105.105 would print and then call above.
      const r = meansReading(100.1, 100.1)
      expect(r.band).toEqual({ low: 95.1, high: 105.1 })
      expect(meansReading(100.1, 105.1).standing).toBe('at')
      expect(meansReading(100.1, 105.11).standing).toBe('above')
      expect(meansReading(100.1, 95.1).standing).toBe('at')
      expect(meansReading(100.1, 95.09).standing).toBe('below')
    })

    it('does not let float dust move a figure across an edge', () => {
      // 0.1 + 0.2 style sums: 5,250.000000001 is 5,250 to the cent.
      expect(meansReading(5000, 5250.000000001).standing).toBe('at')
      expect(meansReading(5000, 4749.999999999).standing).toBe('at')
    })

    it('states the net to the cent', () => {
      expect(meansReading(1000.1, 999.9).net).toBe(0.2)
    })
  })

  it('words the net as left over or short, through the page formatter', () => {
    const money = (n: number) => `$${n.toFixed(2)}`
    expect(netPhrase(820, money)).toBe('$820.00 left over')
    expect(netPhrase(0, money)).toBe('$0.00 left over')
    expect(netPhrase(-300, money)).toBe('$300.00 short')
    expect(netPhrase(-300, () => '$•••')).toBe('$••• short')
  })

  it('bands debt payments alone like any other outflow', () => {
    // Spending 0, a 1,000 mortgage payment: outflows are the payment.
    expect(meansReading(1000, 0 + 1000).standing).toBe('at')
    expect(meansReading(1000, 0 + 1100).standing).toBe('above')
  })

  describe('the margin never contradicts the verdict at the band edges', () => {
    it.each([
      // income 5,000, band 4,750 to 5,250
      [4750, 5, 'under', 'at'],
      [4749.99, 6, 'under', 'below'],
      [5250, 5, 'over', 'at'],
      [5250.01, 6, 'over', 'above'],
    ] as const)('outflows %s read %i%% %s and %s', (outflows, pct, direction, standing) => {
      const r = meansReading(5000, outflows)
      expect(r.standing).toBe(standing)
      expect(r.margin).toEqual({ pct, direction })
    })

    it('rounds a hair of a percent away from zero, never to nothing', () => {
      // One cent under on 5,000 is 0.0002% — still under, so it prints 1%.
      expect(meansReading(5000, 4999.99).margin).toEqual({ pct: 1, direction: 'under' })
      expect(meansReading(5000, 5000.01).margin).toEqual({ pct: 1, direction: 'over' })
    })

    it('reads an exact percentage as itself, not one more', () => {
      expect(meansReading(5000, 4400).margin).toEqual({ pct: 12, direction: 'under' })
      expect(meansReading(3, 2.01).margin).toEqual({ pct: 33, direction: 'under' })
    })

    it('is even only to the cent', () => {
      expect(meansReading(5000, 5000).margin).toEqual({ pct: 0, direction: 'even' })
      expect(meansReading(5000, 5000.000000001).margin).toEqual({ pct: 0, direction: 'even' })
    })
  })

  describe('the margin in words', () => {
    it.each([
      [{ pct: 12, direction: 'under' }, '12% under income', 'Outflows were 88% of income'],
      [{ pct: 4, direction: 'over' }, '4% over income', 'Outflows were 104% of income'],
      [{ pct: 0, direction: 'even' }, 'even with income', 'Outflows were 100% of income'],
    ] as [MeansMargin, string, string][])('%o', (margin, phrase, share) => {
      expect(marginPhrase(margin)).toBe(phrase)
      expect(outflowSharePhrase(margin)).toBe(share)
    })

    it('states a share and a margin that always sum to 100', () => {
      for (const outflows of [0, 1, 4749.99, 4750, 4999.99, 5000, 5250.01, 7333.33, -50]) {
        const margin = meansReading(5000, outflows).margin!
        const share = Number(/(-?\d+)%/.exec(outflowSharePhrase(margin))![1])
        const signed = margin.direction === 'over' ? -margin.pct : margin.pct
        expect(share + signed).toBe(100)
      }
    })

    it('puts the net and the margin on one line, through the page formatter', () => {
      const money = (n: number) => `$${n.toFixed(2)}`
      expect(meansLine(5000, 4180, money)).toBe('$820.00 left over · 17% under income')
      expect(meansLine(5000, 5200, money)).toBe('$200.00 short · 4% over income')
      expect(meansLine(5000, 5000, money)).toBe('$0.00 left over · even with income')
      // No income, no margin: only the net is a fact.
      expect(meansLine(0, 300, money)).toBe('$300.00 short')
    })
  })
})

describe('meansTrend', () => {
  const m = (month: string, income: number, outflows: number) => ({ month, income, outflows })

  it('signs each bar so that up is kept, and skips months with no income', () => {
    const t = meansTrend([
      m('2026-01-01', 5000, 4400),
      m('2026-02-01', 5000, 5200),
      m('2026-03-01', 0, 900),
    ])
    expect(t.bars.map((b) => [b.marginPct, b.reading.standing])).toEqual([
      [12, 'below'],
      [-4, 'at'],
      [null, 'unknown'],
    ])
    expect(t.monthsWithIncome).toBe(2)
    expect(t.belowCount).toBe(1)
  })

  it('counts below-your-means months only among months with income', () => {
    const t = meansTrend([
      m('2026-01-01', 0, 0),
      m('2026-02-01', 0, 400),
      m('2026-03-01', 3000, 2000),
      m('2026-04-01', 3000, 3500),
    ])
    expect(t.belowCount).toBe(1)
    expect(t.monthsWithIncome).toBe(2)
  })

  it('pools the newest three months rather than averaging their percentages', () => {
    // 10% under on 5,000; 50% over on 500; 0% on 5,000. The mean of the
    // three percentages is 13% over; pooled it is 250 kept on 10,500.
    const t = meansTrend([
      m('2026-01-01', 5000, 4500),
      m('2026-02-01', 500, 750),
      m('2026-03-01', 5000, 5000),
    ])
    expect(t.recent.margin).toEqual({ pct: 3, direction: 'under' })
    expect(t.recent.standing).toBe('at')
    expect(t.recent.net).toBe(250)
    expect(t.prior).toBeNull()
    expect(t.direction).toBeNull()
  })

  it('pools in cents, so float dust never moves the headline', () => {
    const t = meansTrend([
      m('2026-01-01', 0.1, 0.1),
      m('2026-02-01', 0.2, 0.2),
      m('2026-03-01', 1000, 1000),
    ])
    expect(t.recent.margin).toEqual({ pct: 0, direction: 'even' })
  })

  it('compares against the three months before, at whole-percent precision', () => {
    const year = [
      m('2025-10-01', 5000, 4800), // prior: 15,000 in, 14,400 out → 4% under
      m('2025-11-01', 5000, 4800),
      m('2025-12-01', 5000, 4800),
      m('2026-01-01', 5000, 4450), // recent: 15,000 in, 13,350 out → 11% under
      m('2026-02-01', 5000, 4450),
      m('2026-03-01', 5000, 4450),
    ]
    const up = meansTrend(year)
    expect(up.recent.margin).toEqual({ pct: 11, direction: 'under' })
    expect(up.prior?.margin).toEqual({ pct: 4, direction: 'under' })
    expect(up.direction).toBe('up')

    expect(meansTrend([...year.slice(3), ...year.slice(0, 3)]).direction).toBe('down')

    // 4.2% and 4.1% under both print 5%: a difference the reader cannot see
    // is not a direction.
    const steady = meansTrend([
      m('2025-12-01', 5000, 4790),
      m('2026-01-01', 5000, 4790),
      m('2026-02-01', 5000, 4790),
      m('2026-03-01', 5000, 4795),
      m('2026-04-01', 5000, 4795),
      m('2026-05-01', 5000, 4795),
    ])
    expect(steady.recent.margin?.pct).toBe(steady.prior?.margin?.pct)
    expect(steady.direction).toBe('steady')
  })

  it('reads a short prior pool from the months that exist', () => {
    const t = meansTrend([
      m('2026-01-01', 1000, 1200),
      m('2026-02-01', 5000, 4000),
      m('2026-03-01', 5000, 4000),
      m('2026-04-01', 5000, 4000),
    ])
    expect(t.prior?.margin).toEqual({ pct: 20, direction: 'over' })
    expect(t.direction).toBe('up')
  })

  it('has no direction when either pool had no income', () => {
    const t = meansTrend([
      m('2026-01-01', 0, 100),
      m('2026-02-01', 5000, 4000),
      m('2026-03-01', 5000, 4000),
      m('2026-04-01', 5000, 4000),
    ])
    expect(t.prior?.standing).toBe('unknown')
    expect(t.direction).toBeNull()
  })

  it('reads no months as unknown with nothing to count', () => {
    const t = meansTrend([])
    expect(t.bars).toEqual([])
    expect(t.recent.standing).toBe('unknown')
    expect(t.prior).toBeNull()
    expect(t.belowCount).toBe(0)
    expect(t.monthsWithIncome).toBe(0)
  })
})
