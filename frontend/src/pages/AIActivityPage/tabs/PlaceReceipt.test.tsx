/**
 * A receipt waiting for an account offers the best answer it has, and any
 * open account besides: the bank's own row first (the receipt goes on it,
 * not beside it as a duplicate), then the account whose card paid.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const place = vi.hoisted(() => vi.fn())

vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [
      { id: 'harborstone', name: 'Harborstone Checking', on_budget: true, is_closed: false },
      { id: 'sapphire', name: 'Sapphire Visa', on_budget: true, is_closed: false },
    ],
  }),
}))
vi.mock('../../../api/aiJobs', () => ({
  usePlaceReceipt: () => ({ mutate: place, isPending: false }),
}))
vi.mock('../../../hooks/useFormatters', () => ({
  useFormatters: () => ({
    formatMoney: (n: number) => `$${Math.abs(n).toFixed(2)}`,
    formatDayMonth: () => 'Sep 20',
  }),
}))

import { PlaceReceipt } from './PlaceReceipt'
import type { AIJob } from '../../../api/aiJobs'

const job = (over: Partial<AIJob> = {}) =>
  ({
    id: 'job-1',
    status: 'unplaced',
    transaction_id: null,
    transaction_account_id: null,
    card_ending_account_id: null,
    bank_match: null,
    result: { draft: { card_last4: '4417' } },
    ...over,
  }) as unknown as AIJob

beforeEach(() => place.mockClear())

describe('PlaceReceipt', () => {
  it('says the receipt is not in the budget yet', () => {
    render(<PlaceReceipt job={job()} budgetId="b1" />)
    expect(screen.getByText('Not in your budget yet — choose where it goes.')).toBeTruthy()
  })

  it("offers the bank's own row first, and puts the receipt on it", () => {
    render(
      <PlaceReceipt
        job={job({
          card_ending_account_id: 'harborstone',
          bank_match: { id: 'txn-9', account_id: 'sapphire', date: '2026-09-20', amount: '-24.00' },
        })}
        budgetId="b1"
      />
    )
    const button = screen.getByRole('button', {
      name: 'Put it on the $24.00 charge in Sapphire Visa on Sep 20',
    })
    expect(screen.queryByText(/Put it in Harborstone/)).toBeNull()
    fireEvent.click(button)
    expect(place.mock.calls[0][0]).toEqual({ jobId: 'job-1', transaction_id: 'txn-9' })
  })

  it('offers the account whose card paid when no row has arrived', () => {
    render(<PlaceReceipt job={job({ card_ending_account_id: 'sapphire' })} budgetId="b1" />)
    fireEvent.click(
      screen.getByRole('button', { name: 'Put it in Sapphire Visa (card ending 4417)' })
    )
    expect(place.mock.calls[0][0]).toEqual({ jobId: 'job-1', account_id: 'sapphire' })
  })

  it('always lets a person choose the account', () => {
    render(<PlaceReceipt job={job()} budgetId="b1" />)
    expect(screen.getByLabelText('Put this receipt in an account')).toBeTruthy()
    expect(screen.queryAllByRole('button', { name: /^Put it/ })).toEqual([])
  })
})
