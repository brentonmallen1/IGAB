import { describe, expect, it } from 'vitest'
import { AT_MEANS_BAND_PCT, meansReading, netPhrase } from './livingMeans'

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
      expect(r.outflowShare).toBeNull()
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
      expect(r.outflowShare).toBe(0)
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
      expect(r.outflowShare).toBe(80)
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
      expect(r.outflowShare).toBe(120)
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
})
