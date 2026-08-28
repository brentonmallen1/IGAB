import { describe, it, expect } from 'vitest'
import { formatSignalFigure, signalHeadline } from './signalHeadline'

const money = (n: number) => `$${n.toFixed(2)}`

describe('signalHeadline', () => {
  it('reads a boolean concept from met, not from a figure it never has', () => {
    // budget_exists is served met=true with no value; SignalNote used to
    // print "not known" beside a reason saying "you have a budget".
    expect(signalHeadline({ met: true, value: null }, 'boolean', money)).toEqual({
      text: 'yes',
      known: true,
    })
  })

  it('says no for a boolean answered no', () => {
    expect(signalHeadline({ met: false, value: null }, 'boolean', money)).toEqual({
      text: 'no',
      known: true,
    })
  })

  it('is not known for a boolean with no answer yet', () => {
    expect(signalHeadline({ met: null, value: null }, 'boolean', money)).toEqual({
      text: 'not known',
      known: false,
    })
  })

  it('reads an amount from its figure, whatever met says', () => {
    expect(signalHeadline({ met: false, value: '1240.5' }, 'amount', money)).toEqual({
      text: '$1240.50',
      known: true,
    })
  })

  it('is not known for an amount with no figure', () => {
    expect(signalHeadline({ met: null, value: null }, 'amount', money)).toEqual({
      text: 'not known',
      known: false,
    })
  })

  it('reads a rate as a percentage', () => {
    expect(signalHeadline({ met: true, value: '15' }, 'rate', money)).toEqual({
      text: '15.0%',
      known: true,
    })
  })
})

describe('formatSignalFigure', () => {
  it('formats money and rates in their own units', () => {
    expect(formatSignalFigure('9600', 'amount', money)).toBe('$9600.00')
    expect(formatSignalFigure('12.25', 'rate', money)).toBe('12.3%')
  })

  it('is null for no figure or one that does not parse', () => {
    expect(formatSignalFigure(null, 'amount', money)).toBeNull()
    expect(formatSignalFigure('n/a', 'amount', money)).toBeNull()
  })
})
