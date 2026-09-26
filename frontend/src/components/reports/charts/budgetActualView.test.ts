import { describe, expect, it } from 'vitest'
import { varianceHeadline } from './budgetActualView'

const money = (n: number) => `$${n.toFixed(2)}`

describe('varianceHeadline', () => {
  it('names an overrun as over plan, by a positive amount', () => {
    expect(varianceHeadline(-120, money)).toEqual({
      label: 'Over plan by',
      value: '$120.00',
      over: true,
    })
  })

  it('names money left in the plan as under plan', () => {
    expect(varianceHeadline(80, money)).toEqual({
      label: 'Under plan by',
      value: '$80.00',
      over: false,
    })
  })

  it('reads exactly on plan as on plan, not as "$0.00" either way', () => {
    expect(varianceHeadline(0, money)).toEqual({
      label: 'Against plan',
      value: 'On plan',
      over: false,
    })
  })

  it('reads float dust as on plan, and a genuine cent as a direction', () => {
    expect(varianceHeadline(0.004, money).value).toBe('On plan')
    expect(varianceHeadline(-0.01, money).label).toBe('Over plan by')
  })
})
