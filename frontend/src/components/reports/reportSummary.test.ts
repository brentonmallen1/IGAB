import { describe, expect, it } from 'vitest'
import { mayPin, pinnedLead, summaryShown } from './reportSummary'

describe('summaryShown', () => {
  it('shows once the row has scrolled up under the header', () => {
    expect(summaryShown(90, 120)).toBe(true)
    expect(summaryShown(120, 120)).toBe(true)
  })

  it('hides while any of the row is still below the header', () => {
    expect(summaryShown(121, 120)).toBe(false)
  })

  it('hides when the observer cannot say where the header ends', () => {
    expect(summaryShown(0, null)).toBe(false)
  })

  it('never summarises a row still below the fold', () => {
    // Out of view, but ahead of the reader rather than behind them.
    expect(summaryShown(1400, 120)).toBe(false)
  })
})

describe('pinnedLead', () => {
  it('is nothing when the controls share the title row', () => {
    // Centred beside a taller title, the controls sit a pixel low.
    expect(pinnedLead(9, 8, 40)).toBe(0)
  })

  it('is everything above the controls row when the header stacks', () => {
    // A phone: title and subtitle (68px) above the controls.
    expect(pinnedLead(76, 8, 36)).toBe(68)
  })

  it('is never negative', () => {
    expect(pinnedLead(40, 60, 30)).toBe(0)
  })
})

describe('mayPin', () => {
  it('pins a header of a line or two', () => {
    // Plan vs Spent's controls on a phone: 82 of a 683px pane.
    expect(mayPin(82, 683)).toBe(true)
    expect(mayPin(45, 719)).toBe(true)
  })

  it('lets a header too tall to pin scroll away', () => {
    // Liabilities' controls on a phone wrapped to four rows: 148 of 683.
    expect(mayPin(148, 683)).toBe(false)
  })

  it('does not forbid pinning before the pane is measured', () => {
    expect(mayPin(148, 0)).toBe(true)
  })
})
