/**
 * Reconciling with receipts still in no account: a purchase paid from this
 * account may be missing from the balance about to be checked, so the
 * question says so first and offers to put each one here.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const h = vi.hoisted(() => ({ jobs: [] as unknown[], place: vi.fn() }))

vi.mock('../../api/aiJobs', () => ({
  useAIJobs: () => ({ data: { jobs: h.jobs } }),
  usePlaceReceipt: () => ({ mutate: h.place, isPending: false }),
}))
vi.mock('../../hooks/useFormatters', () => ({
  useFormatters: () => ({
    formatMoney: (n: number) => `-$${Math.abs(n).toFixed(2)}`,
    formatDayMonth: (d: string) => d.slice(5),
  }),
}))

import { WaitingReceiptsNote } from './WaitingReceiptsNote'

const waiting = (id: string, payee: string, cardOwner: string | null = null) => ({
  id,
  status: 'unplaced',
  card_ending_account_id: cardOwner,
  result: { draft: { payee, amount: '-24.00', date: '2026-09-20' } },
})

const renderNote = () =>
  render(
    <MemoryRouter>
      <WaitingReceiptsNote budgetId="b1" accountId="sapphire" accountName="Sapphire Visa" />
    </MemoryRouter>
  )

beforeEach(() => {
  h.place.mockClear()
  h.jobs = []
})

describe('WaitingReceiptsNote', () => {
  it('says nothing when no receipt is waiting', () => {
    const { container } = renderNote()
    expect(container.textContent).toBe('')
  })

  it('warns, and puts a receipt in this account with one tap', () => {
    h.jobs = [waiting('j1', 'Hardware Store')]
    renderNote()
    expect(
      screen.getByText(
        /1 scanned receipt isn’t in any account yet\. If one was paid from Sapphire Visa, this balance doesn’t include it\./
      )
    ).toBeTruthy()
    expect(screen.getByText('Hardware Store · -$24.00 · 09-20')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'It’s from here' }))
    expect(h.place.mock.calls[0][0]).toEqual({ jobId: 'j1', account_id: 'sapphire' })
  })

  it("lists this account's own card first, and sends the rest to AI Activity", () => {
    h.jobs = [
      waiting('j1', 'Bakery'),
      waiting('j2', 'Garden Centre'),
      waiting('j3', 'Hardware Store', 'sapphire'),
      waiting('j4', 'Pharmacy'),
    ]
    renderNote()
    const rows = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(rows[0]).toMatch(/^Hardware Store/)
    expect(rows).toHaveLength(3)
    expect(screen.getByRole('link', { name: '1 more in AI Activity' })).toBeTruthy()
  })

  it("puts it on the bank's row when that row is already in this account", () => {
    h.jobs = [
      {
        ...waiting('j1', 'Corner Grocer'),
        bank_match: { id: 'txn-9', account_id: 'sapphire', date: '2026-09-22', amount: '-24.00' },
      },
    ]
    renderNote()
    fireEvent.click(screen.getByRole('button', { name: 'It’s the 09-22 charge' }))
    expect(h.place.mock.calls[0][0]).toEqual({ jobId: 'j1', transaction_id: 'txn-9' })
  })

  it("still offers a new row when the matched row is another account's", () => {
    h.jobs = [
      {
        ...waiting('j1', 'Corner Grocer'),
        bank_match: {
          id: 'txn-9',
          account_id: 'harborstone',
          date: '2026-09-22',
          amount: '-24.00',
        },
      },
    ]
    renderNote()
    fireEvent.click(screen.getByRole('button', { name: 'It’s from here' }))
    expect(h.place.mock.calls[0][0]).toEqual({ jobId: 'j1', account_id: 'sapphire' })
  })
})
