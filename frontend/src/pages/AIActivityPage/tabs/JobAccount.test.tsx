/**
 * The review list has to name the account.
 *
 * Nothing about an AI draft chooses the account — the model reads a payee, an
 * amount, a date and a category off the receipt, and the account is whatever
 * was selected before the photo was taken. So it is the field most worth
 * checking before approving, and it was the one field the row never showed:
 * a receipt filed against the wrong card was approved looking perfectly
 * correct, and surfaced later as a balance that did not match.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const move = vi.hoisted(() => vi.fn())

vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [
      { id: 'acc-1', name: 'Harborstone Checking', on_budget: true, is_closed: false },
      { id: 'acc-2', name: 'Sapphire Visa', on_budget: true, is_closed: false },
    ],
  }),
}))
vi.mock('../../../hooks/useAccountMove', () => ({ useAccountMove: () => move }))

import { JobAccount } from './JobAccount'
import type { AIJob } from '../../../api/aiJobs'

const JOB = {
  id: 'job-1',
  kind: 'receipt',
  status: 'done',
  payload: { account_id: 'acc-1' },
  transaction_id: 'txn-1',
  transaction_account_id: 'acc-2',
  needs_review: true,
} as unknown as AIJob

function renderJob(overrides: Partial<AIJob> = {}) {
  return render(<JobAccount job={{ ...JOB, ...overrides } as AIJob} budgetId="b1" />)
}

beforeEach(() => move.mockClear())

describe('JobAccount', () => {
  it('names the account the transaction is in now, not the one it was scanned against', () => {
    // The whole reason the field is served: the payload records where the
    // scan was submitted, which a move leaves behind.
    renderJob()
    expect(screen.getByText('Sapphire Visa')).toBeTruthy()
    expect(screen.queryByText('Harborstone Checking')).toBeNull()
  })

  it('falls back to the submitted account while the transaction does not exist yet', () => {
    // A queued scan has no row. The payload is then a statement of where the
    // row will go, which is still worth seeing before it gets there.
    renderJob({ transaction_id: null, transaction_account_id: null })
    expect(screen.getByText('Harborstone Checking')).toBeTruthy()
  })

  it('offers the move on a row still waiting for approval', () => {
    renderJob()
    fireEvent.click(screen.getByRole('button', { name: /Sapphire Visa/ }))
    expect(screen.getByRole('combobox', { name: 'Move to account' })).toBeTruthy()
  })

  it('reads out, but does not offer a move, once the row has been approved', () => {
    // An approved row is edited in its register like any other.
    renderJob({ needs_review: false })
    expect(screen.getByText('Sapphire Visa')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Sapphire Visa/ })).toBeNull()
  })
})
