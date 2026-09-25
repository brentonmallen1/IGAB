import { describe, expect, it } from 'vitest'
import { burnChange, burnChangeLine, burnPriorLine, signedWholePercent } from './burnRateView'

const money = (n: number) =>
  `${n < 0 ? '−' : ''}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

describe('signedWholePercent', () => {
  it('signs a change and rounds it to whole percent', () => {
    expect(signedWholePercent(8.4)).toBe('+8%')
    expect(signedWholePercent(-12.6)).toBe('−13%')
  })

  it('reads a change that rounds to nothing as 0%, never −0%', () => {
    expect(signedWholePercent(0)).toBe('0%')
    expect(signedWholePercent(-0.4)).toBe('0%')
    expect(signedWholePercent(0.4)).toBe('0%')
  })
})

describe('burnChange', () => {
  it('is the last 30 days against the prior 60 days’ pace', () => {
    // $900 against $600 per 30 days: half as fast again.
    expect(burnChange(900, 600)).toBe('+50%')
    expect(burnChange(450, 600)).toBe('−25%')
  })

  it('has no percentage without prior spending to compare with', () => {
    expect(burnChange(900, 0)).toBeNull()
    // Refunds outweighing spending over the prior 60 days: still nothing to
    // take a percentage of.
    expect(burnChange(900, -40)).toBeNull()
  })
})

describe('burnPriorLine', () => {
  it('names the prior pace and the change on the Overview card', () => {
    expect(burnPriorLine(900, 600, money)).toBe('Prior 60 days: $600.00/30d · +50%')
  })

  it('shows the prior figure alone when it is zero', () => {
    expect(burnPriorLine(900, 0, money)).toBe('Prior 60 days: $0.00/30d')
  })
})

describe('burnChangeLine', () => {
  it('states the change on the Burn Rate tab’s 30-day card', () => {
    expect(burnChangeLine(900, 600)).toBe('+50% on the prior 60 days')
  })

  it('says why there is no change rather than printing 0%', () => {
    expect(burnChangeLine(900, 0)).toBe('No spending in the prior 60 days')
  })
})
