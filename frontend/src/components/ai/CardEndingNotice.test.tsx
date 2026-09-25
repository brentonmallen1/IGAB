import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const move = vi.hoisted(() => vi.fn())
const create = vi.hoisted(() => vi.fn())

vi.mock('../../api/accounts', () => ({
  useAccounts: () => ({
    data: [
      { id: 'harborstone', name: 'Harborstone Checking' },
      { id: 'sapphire', name: 'Sapphire Visa' },
    ],
  }),
}))
vi.mock('../../hooks/useAccountMove', () => ({ useAccountMove: () => move }))
vi.mock('../../api/cardEndings', () => ({
  useCreateCardEnding: () => ({ mutate: create, isPending: false }),
}))

import { CardEndingNotice } from './CardEndingNotice'
import type { AIJob } from '../../api/aiJobs'

const job = (over: Partial<AIJob> = {}) =>
  ({
    id: 'job-1',
    transaction_id: 'txn-1',
    transaction_account_id: 'harborstone',
    card_ending_account_id: null,
    needs_review: true,
    result: { draft: { card_last4: '4417' } },
    ...over,
  }) as AIJob

beforeEach(() => {
  move.mockClear()
  create.mockClear()
})

describe('CardEndingNotice', () => {
  it('offers to remember an unknown ending for the account the scan is in', () => {
    render(<CardEndingNotice job={job()} budgetId="b1" canMove />)
    expect(screen.getByText('Paid with a card ending 4417.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Remember it for Harborstone Checking' }))
    expect(create.mock.calls[0][0]).toEqual({ account_id: 'harborstone', last4: '4417' })
  })

  it("names the owner and moves the scan there when it is another account's card", () => {
    render(
      <CardEndingNotice job={job({ card_ending_account_id: 'sapphire' })} budgetId="b1" canMove />
    )
    expect(
      screen.getByText(
        'Paid with the card ending 4417, which is on Sapphire Visa, not Harborstone Checking.'
      )
    ).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Move to Sapphire Visa' }))
    expect(move).toHaveBeenCalledWith({ id: 'txn-1', account_id: 'harborstone' }, 'sapphire')
  })

  it('offers no move inside the editor, which owns its own Account field', () => {
    render(
      <CardEndingNotice
        job={job({ card_ending_account_id: 'sapphire' })}
        budgetId="b1"
        canMove={false}
      />
    )
    expect(screen.queryByRole('button', { name: /Move to/ })).toBeNull()
  })

  it('says nothing once the scan is approved — the moment to ask has passed', () => {
    const { container } = render(
      <CardEndingNotice job={job({ needs_review: false })} budgetId="b1" canMove />
    )
    expect(container.textContent).toBe('')
  })
})
