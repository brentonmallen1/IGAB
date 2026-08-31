/**
 * The two overspending chips read as "$120.00 overspent", not
 * "$120.00overspent".
 *
 * Both chips are `display: inline-flex`, so the amount and the word are
 * separate flex items — and leading whitespace inside a flex item is
 * stripped. The separator was written as a literal space in the JSX, where it
 * had no effect; it now lives once, as `gap`, in TbaHero.css.
 *
 * So the assertion here is that the markup carries NO separator: jsdom does
 * not lay out `gap`, and a space reappearing in the JSX is exactly the
 * regression this pins. The CSS is where the space is allowed to come from.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { BudgetMonth } from '../../../types'

const month = vi.hoisted(() => ({ current: {} as Partial<BudgetMonth> }))

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: month.current }),
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../AssignDropdown/AssignDropdown', () => ({
  AssignDropdown: () => null,
  AssignDropdownContent: () => null,
}))
vi.mock('../AssignPreviewModal/AssignPreviewModal', () => ({
  AssignPreviewModal: () => null,
}))
vi.mock('./CoverOverspentModal', () => ({ CoverOverspentModal: () => null }))
vi.mock('./TbaDrawer', () => ({ TbaDrawer: () => null }))

import { TbaHero } from './TbaHero'

beforeEach(() => {
  month.current = {
    to_be_assigned: 0,
    total_overspent_cash: 120.0,
    total_overspent_credit: 45.0,
    overspent_count_cash: 1,
  } as unknown as BudgetMonth
})

describe('TbaHero overspending chips', () => {
  it('puts no separator in the markup — the space is the flex gap', () => {
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    for (const word of ['overspent', 'on cards']) {
      const span = screen.getByText(word)
      expect(span.textContent).toBe(word)
      expect(span.className).toContain('tba-hero__chip-word')
    }
  })

  it('still renders both amounts beside their words', () => {
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    expect(screen.getByText('overspent').parentElement?.textContent).toBe('-$120.00overspent')
    expect(screen.getByText('on cards').parentElement?.textContent).toBe('-$45.00on cards')
  })

  it('says nothing when nothing is overspent', () => {
    month.current = { to_be_assigned: 0 } as unknown as BudgetMonth
    render(<TbaHero budgetId="b1" month="2026-08-01" />)

    expect(screen.queryByText('overspent')).toBeNull()
    expect(screen.queryByText('on cards')).toBeNull()
  })
})
