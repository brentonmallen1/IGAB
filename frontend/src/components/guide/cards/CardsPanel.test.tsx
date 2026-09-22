/**
 * The Credit cards tab: pick how you use the card, then read what can happen.
 *
 * The order is the design. Most of what confuses people about card figures is
 * being shown a state that cannot happen to them — so the intent filter has to
 * actually narrow, and the walkthrough has to render served figures rather
 * than any of its own.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { CardExamples } from '../../../api/guide'

const data = vi.hoisted(() => ({ current: null as CardExamples | null }))

vi.mock('../../../api/guide', () => ({
  useCardExamples: () => ({ data: data.current, isLoading: false }),
}))
// Selector-aware: a mock that answers every selector with the budget id also
// answers `privacyMode` with it, and every figure renders masked.
vi.mock('../../../stores/appStore', () => ({
  useAppStore: (select: (s: { currentBudgetId: string; privacyMode: boolean }) => unknown) =>
    select({ currentBudgetId: 'b1', privacyMode: false }),
}))

import { CardsPanel } from './CardsPanel'

const EXAMPLES: CardExamples = {
  intents: [
    { id: 'in-full', label: 'I pay it off every month', detail: 'The card is a convenience.' },
    { id: 'paying-down', label: "I'm paying a balance down", detail: 'Old debt comes down.' },
  ],
  examples: [
    {
      slug: 'paid-in-full',
      title: 'Funded spending, paid every month',
      story: 'The shape everything else departs from.',
      card: 'Cedar Point Visa',
      intents: ['in-full'],
      opening: 0,
      months: [
        {
          month: '2026-08-01',
          label: 'Last month',
          steps: [{ kind: 'fund', amount: 200, category: 'Groceries', day: 1, says: 'Budget $200.00 into Groceries' }],
          set_aside: 200,
          balance: -200,
          uncovered: 0,
          over_reserved: 0,
          short_reserved: 0,
          card_credit: 0,
          riding: 0,
        },
        {
          month: '2026-09-01',
          label: 'This month',
          steps: [],
          set_aside: 200,
          balance: -200,
          uncovered: 0,
          over_reserved: 0,
          short_reserved: 0,
          card_credit: 0,
          riding: 0,
        },
      ],
    },
    {
      slug: 'carrying-debt',
      title: 'Old debt, paid down by assigning to the card',
      story: 'The card arrived with a balance the budget never funded.',
      card: 'Harborstone Card',
      intents: ['paying-down'],
      opening: -3000,
      months: [
        {
          month: '2026-09-01',
          label: 'This month',
          steps: [{ kind: 'assign', amount: 250, category: null, day: 1, says: 'Assign $250.00 to the card' }],
          set_aside: 350,
          balance: -2600,
          uncovered: 2250,
          over_reserved: 0,
          short_reserved: 0,
          card_credit: 0,
          riding: 0,
        },
      ],
    },
  ],
}

function renderPanel() {
  data.current = EXAMPLES
  return render(
    <MemoryRouter>
      <CardsPanel />
    </MemoryRouter>
  )
}

describe('the Credit cards tab', () => {
  it('lists every situation before a way of using the card is picked', () => {
    renderPanel()
    expect(screen.getByText('Funded spending, paid every month')).toBeInTheDocument()
    expect(screen.getByText('Old debt, paid down by assigning to the card')).toBeInTheDocument()
  })

  it('narrows to the situations that can happen to this reader', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: "I'm paying a balance down" }))
    expect(screen.getByText('Old debt, paid down by assigning to the card')).toBeInTheDocument()
    expect(screen.queryByText('Funded spending, paid every month')).toBeNull()
  })

  it('says what working looks like for the way you picked', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'I pay it off every month' }))
    expect(screen.getByText('The card is a convenience.')).toBeInTheDocument()
  })

  it('goes back to every situation when the choice is unpicked', async () => {
    renderPanel()
    const pick = screen.getByRole('button', { name: 'I pay it off every month' })
    await userEvent.click(pick)
    expect(screen.queryByText('Old debt, paid down by assigning to the card')).toBeNull()
    await userEvent.click(pick)
    expect(screen.getByText('Old debt, paid down by assigning to the card')).toBeInTheDocument()
  })

  it('walks the months, showing only the served figures', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /Old debt, paid down/ }))
    // Every figure comes from the served month — the panel computes none.
    expect(screen.getByText('$350.00')).toBeInTheDocument()
    expect(screen.getByText('-$2,600.00')).toBeInTheDocument()
    expect(screen.getByText('$2,250.00')).toBeInTheDocument()
    expect(screen.getByText('Assign $250.00 to the card')).toBeInTheDocument()
  })

  it('says so plainly when a month had nothing happen in it', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /Funded spending/ }))
    await userEvent.click(screen.getByRole('tab', { name: 'This month' }))
    expect(screen.getByText('Nothing happened on the card this month.')).toBeInTheDocument()
  })

  it('names Spare only when the card holds more than it owes', async () => {
    renderPanel()
    await userEvent.click(screen.getByRole('button', { name: /Old debt, paid down/ }))
    const figures = screen.getByText('$350.00').closest('.card-walk__figures') as HTMLElement
    expect(within(figures).queryByText('Spare')).toBeNull()
  })
})
