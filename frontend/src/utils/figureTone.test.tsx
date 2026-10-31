/**
 * The one colour rule for budget figures. Each divergence the fourteen hand
 * copies had is a case here, named for the component that got it wrong.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import {
  BUDGET_COLOR_MODES,
  alarmOnly,
  availableTone,
  figureClass,
  normalizeBudgetColorMode,
  signTone,
} from './figureTone'
import { sumBalances } from '../components/budget/budgetTotals'
import { BalanceBreakdownRows } from '../components/budget/CategoryInspector/BalanceBreakdownRows'
import { makeCategoryBalance } from '../test-utils/factories'

describe('availableTone', () => {
  const tone = (available: number | null, credit_overspent = 0) =>
    availableTone({ available, credit_overspent })

  it('reads money left as positive and an empty envelope as zero', () => {
    expect(tone(0.01)).toBe('positive')
    expect(tone(0)).toBe('zero')
  })

  it("reads an income category's missing figure as zero, not as red", () => {
    expect(tone(null)).toBe('zero')
  })

  it('reads a cash overspend as the alarm', () => {
    expect(tone(-42)).toBe('negative')
  })

  it('reads red swiped entirely on a card as calm', () => {
    expect(tone(-42, 42)).toBe('negative-on-card')
    expect(tone(-42, 60)).toBe('negative-on-card')
  })

  it('still alarms when only part of the red rode on a card', () => {
    // The cash cent is what charges Ready to Assign.
    expect(tone(-42, 41.99)).toBe('negative')
  })

  it('ignores card spending on an envelope that is not negative', () => {
    expect(tone(10, 25)).toBe('positive')
  })
})

describe('signTone', () => {
  it('reads a Ready to Assign of zero as zero — AssignPreviewModal and CoverOverspentModal drew it green', () => {
    // `>= 0 ? 'positive'` in both dialogs, while TbaHero drew the same zero muted.
    expect(signTone(0)).toBe('zero')
    expect(figureClass('balance', signTone(0))).not.toContain('positive')
  })

  it('reads a zero row as zero — TransactionsPeekModal drew $0.00 green', () => {
    expect(figureClass('flow', signTone(0))).toBe('budget-figure budget-figure--flow zero')
  })

  it('reads the sign and nothing else', () => {
    expect(signTone(0.01)).toBe('positive')
    expect(signTone(-0.01)).toBe('negative')
  })
})

describe('a total of envelopes', () => {
  const row = (available: number, credit_overspent = 0) =>
    makeCategoryBalance({ assigned: 0, activity: available, available, credit_overspent })

  it('reads calm when a card is the whole reason it is red — MultiMonthSheet and CategoryGroupRow drew it as the alarm', () => {
    // A -$42 envelope swiped on a card, a +$10 one beside it: the group is -$32,
    // and every cent of it rode on the card. The grid's rows already read calm.
    expect(availableTone(sumBalances([row(-42, 42), row(10)]))).toBe('negative-on-card')
  })

  it('still alarms when cash is behind part of the red', () => {
    // -$42 on a card and -$8 in cash: adding the card back leaves -$8.
    expect(availableTone(sumBalances([row(-42, 42), row(-8)]))).toBe('negative')
  })

  it('reads a positive total as positive whatever rode on a card', () => {
    expect(availableTone(sumBalances([row(-42, 42), row(100)]))).toBe('positive')
  })
})

describe('alarmOnly', () => {
  it('keeps the warning half and drops the rest — HistorySection and the quick-add toast', () => {
    // Receipts, not readings: a column of green would celebrate every month.
    expect(alarmOnly('negative')).toBe('negative')
    expect(alarmOnly('negative-on-card')).toBe('negative-on-card')
    expect(alarmOnly('positive')).toBeNull()
    expect(alarmOnly('zero')).toBeNull()
  })
})

describe('figureClass', () => {
  it('names the role so the colour setting can quiet one kind', () => {
    expect(figureClass('flow', 'negative')).toBe('budget-figure budget-figure--flow negative')
    expect(figureClass('balance', 'positive')).toBe('budget-figure budget-figure--balance positive')
  })

  it('is plain for no tone, in every mode', () => {
    expect(figureClass('balance', null)).toBe('')
  })
})

describe('the inspector breakdown', () => {
  const totals = sumBalances([
    makeCategoryBalance({ assigned: 200, activity: 35, available: 235, credit_overspent: 0 }),
  ])

  it('draws Assigned plain and a refund green, as the grid does — the inspector painted Assigned and left refunds plain', () => {
    render(
      <BalanceBreakdownRows
        totals={totals}
        labels={{ leftOver: 'Left over', assigned: 'Assigned', activity: 'Activity' }}
      />
    )
    const assigned = screen.getByText('Assigned').nextElementSibling!
    const activity = screen.getByText('Activity').nextElementSibling!
    expect(assigned.className).not.toMatch(/positive|negative|budget-figure/)
    expect(activity.className).toContain('budget-figure--flow positive')
  })
})

describe('the colour modes', () => {
  it('reads anything it does not know as full colour', () => {
    expect(normalizeBudgetColorMode('available')).toBe('available')
    expect(normalizeBudgetColorMode('mono')).toBe('full')
    expect(normalizeBudgetColorMode(undefined)).toBe('full')
  })

  it('are three: both roles, balances only, neither', () => {
    expect([...BUDGET_COLOR_MODES]).toEqual(['full', 'available', 'none'])
  })
})
