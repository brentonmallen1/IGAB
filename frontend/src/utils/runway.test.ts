import { describe, expect, it } from 'vitest'
import { runwayFigure } from '../test-utils/runwayFixtures'
import {
  RUNWAY_MONEY_OPTIONS,
  RUNWAY_SPENDING_OPTIONS,
  fundCoverLine,
  runwayBasis,
  runwayMonths,
  runwayStatement,
} from './runway'

const date = (d: string) => `D(${d})`

describe('runwayStatement', () => {
  it('states the months and the date the money runs out', () => {
    expect(runwayStatement(runwayFigure(), date)).toEqual({
      value: '20.0 months',
      detail: 'to D(2028-05-27)',
      gone: false,
    })
  })

  it('says the money is gone when the cards owe as much as it holds, or more', () => {
    // Days Until Zero hid itself here once — the moment its answer mattered.
    const gone = runwayFigure({ money_total: -300, months: 0, runs_out_on: '2026-09-26' })
    expect(runwayStatement(gone, date)).toEqual({
      value: '0.0 months',
      detail: 'Nothing left once the cards are paid',
      gone: true,
    })
    expect(runwayStatement(runwayFigure({ money_total: 0, months: 0 }), date).gone).toBe(true)
  })

  it('does not call a few days of money gone, though it rounds to 0.0 months', () => {
    const few = runwayFigure({ money_total: 25, months: 0, runs_out_on: '2026-09-27' })
    expect(runwayStatement(few, date)).toEqual({
      value: '0.0 months',
      detail: 'to D(2026-09-27)',
      gone: false,
    })
  })

  it('never states zero for a fund nobody chose', () => {
    const unchosen = runwayFigure({ money: 'with_fund', money_total: null, months: null })
    expect(runwayStatement(unchosen, date)).toEqual({
      value: '—',
      detail: 'No emergency fund chosen',
      gone: false,
    })
  })

  it('never states zero for a tier nothing is tagged into', () => {
    const lean = runwayFigure({ spending: 'essentials', monthly_spending: null, months: null })
    expect(runwayStatement(lean, date).detail).toBe('Nothing tagged Essential')
    const living = runwayFigure({
      spending: 'cost_of_living',
      monthly_spending: null,
      months: null,
    })
    expect(runwayStatement(living, date).detail).toBe('Nothing tagged Essential or Cost of living')
  })

  it('says nothing is being spent rather than printing a huge number', () => {
    const idle = runwayFigure({ monthly_spending: 0, months: null, runs_out_on: null })
    expect(runwayStatement(idle, date)).toEqual({
      value: '—',
      detail: 'Nothing spent to run out at',
      gone: false,
    })
  })
})

describe('runwayBasis', () => {
  it('names the spending, the money and the cards every time', () => {
    expect(runwayBasis({ spending: 'essentials', money: 'with_fund' })).toBe(
      'Essentials, checking + emergency fund, cards paid'
    )
    expect(runwayBasis({ spending: 'all', money: 'checking' })).toBe(
      'all spending, checking, cards paid'
    )
    expect(runwayBasis({ spending: 'cost_of_living', money: 'with_savings' })).toBe(
      'cost of living, checking + all savings, cards paid'
    )
    expect(runwayBasis({ spending: 'essentials', money: 'fund' })).toBe(
      'Essentials, emergency fund, cards paid'
    )
  })
})

describe('runwayMonths', () => {
  it('keeps the served decimal', () => {
    expect(runwayMonths(20)).toBe('20.0 months')
    expect(runwayMonths(6.5)).toBe('6.5 months')
    expect(runwayMonths(1)).toBe('1.0 month')
  })
})

describe('the pickers', () => {
  it('offer three spendings and three moneys, never the fund alone', () => {
    expect(RUNWAY_SPENDING_OPTIONS.map((o) => o.label)).toEqual([
      'All',
      'Cost of living',
      'Essentials',
    ])
    expect(RUNWAY_MONEY_OPTIONS.map((o) => o.label)).toEqual([
      'Checking',
      '+ Emergency fund',
      '+ All savings',
    ])
    expect(RUNWAY_MONEY_OPTIONS.map((o) => o.value)).not.toContain('fund')
  })
})

describe('fundCoverLine', () => {
  it('says how long the fund lasts on Essentials, cards paid', () => {
    const fund = runwayFigure({ money: 'fund', money_total: 6500, months: 6.5 })
    expect(fundCoverLine(fund)).toBe('6.5 months of essentials, cards paid')
  })

  it('says why there is no figure', () => {
    expect(fundCoverLine(runwayFigure({ money_total: null, months: null }))).toBe(
      'No emergency fund chosen'
    )
    expect(fundCoverLine(runwayFigure({ money_total: -100, months: 0 }))).toBe(
      'Nothing left once the cards are paid'
    )
  })
})
