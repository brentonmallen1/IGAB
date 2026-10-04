/**
 * The import month names the rows that arrived from before the budget
 * started, so an envelope never moves for money nobody can find. Dismissal is
 * per device and lasts until more arrive.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LateArrival } from '../../../types'
import { LateArrivalsNote } from './LateArrivalsNote'

vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({ data: [{ id: 'a1', name: 'Harborstone Checking' }] }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: [{ id: 'c1', name: 'Groceries' }] }),
}))
vi.mock('../../../api/payees', () => ({
  usePayees: () => ({ data: [{ id: 'p1', name: 'Corner Market' }] }),
}))

const arrival = (id: string, over: Partial<LateArrival> = {}): LateArrival => ({
  transaction_id: id,
  date: '2026-06-28',
  amount: -40,
  account_id: 'a1',
  category_id: 'c1',
  payee_id: 'p1',
  ...over,
})

describe('the import month’s late arrivals', () => {
  beforeEach(() => window.localStorage.clear())

  it('says what arrived and where it counts', () => {
    render(<LateArrivalsNote budgetId="b1" month="2026-07-01" arrivals={[arrival('t1')]} />)
    expect(
      screen.getByText(/One transaction dated in June 2026 arrived after your import/)
    ).toBeInTheDocument()
    expect(screen.getByText('Corner Market')).toBeInTheDocument()
    expect(screen.getByText('Groceries')).toBeInTheDocument()
  })

  it('names an unfiled one as needing a category', () => {
    render(
      <LateArrivalsNote
        budgetId="b1"
        month="2026-07-01"
        arrivals={[arrival('t1', { category_id: null })]}
      />
    )
    expect(screen.getByText('Needs a category')).toBeInTheDocument()
  })

  it('stays dismissed until another arrives', () => {
    const { rerender } = render(
      <LateArrivalsNote budgetId="b1" month="2026-07-01" arrivals={[arrival('t1')]} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByRole('region')).not.toBeInTheDocument()

    rerender(<LateArrivalsNote budgetId="b1" month="2026-07-01" arrivals={[arrival('t1')]} />)
    expect(screen.queryByText(/arrived after your import/)).not.toBeInTheDocument()

    rerender(
      <LateArrivalsNote
        budgetId="b1"
        month="2026-07-01"
        arrivals={[arrival('t1'), arrival('t2')]}
      />
    )
    expect(screen.getByText(/2 transactions dated in June 2026/)).toBeInTheDocument()
  })

  it('draws nothing on a month with none', () => {
    const { container } = render(
      <LateArrivalsNote budgetId="b1" month="2026-07-01" arrivals={[]} />
    )
    expect(container).toBeEmptyDOMElement()
  })
})
