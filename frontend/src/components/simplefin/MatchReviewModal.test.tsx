/**
 * Accept link and Keep separate sat inside the scrolling card, drawn in their
 * own button style, while Previous and Next were borderless text in the
 * footer — on a tall card the decision scrolled away from the queue controls.
 * The decision is the footer's now, in the shared dialog buttons.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { TransactionMatch } from '../../types'
import { MatchReviewModal } from './MatchReviewModal'

const api = vi.hoisted(() => ({
  accept: vi.fn((_: string) => Promise.resolve({})),
  reject: vi.fn((_: string) => Promise.resolve({})),
}))
vi.mock('../../api/simplefin', () => ({
  useAcceptMatch: () => ({ mutateAsync: api.accept, isPending: false }),
  useRejectMatch: () => ({ mutateAsync: api.reject, isPending: false }),
}))
vi.mock('../../api/payees', () => ({ usePayees: () => ({ data: [] }) }))
vi.mock('../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../../api/transactions', () => ({
  useTransaction: () => ({ data: undefined, isLoading: false }),
}))

const match = (id: string): TransactionMatch => ({
  id,
  synced_transaction_id: `s-${id}`,
  manual_transaction_id: `m-${id}`,
  confidence_score: 0.9,
  status: 'pending',
  created_at: '2026-09-01T00:00:00Z',
})

beforeEach(async () => {
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  api.accept.mockClear()
  api.reject.mockClear()
})

describe('MatchReviewModal', () => {
  it('decides in the footer, in the shared buttons', () => {
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={vi.fn()} />)
    const accept = screen.getByRole('button', { name: 'Accept link' })
    const keep = screen.getByRole('button', { name: 'Keep separate' })
    expect(accept).toHaveClass('dialog-btn', 'dialog-btn--primary')
    expect(keep).toHaveClass('dialog-btn', 'dialog-btn--secondary')
    expect(accept.closest('.dialog-actions__end')).not.toBeNull()
    // Only one match: nothing to move between.
    expect(screen.queryByRole('button', { name: 'Next match' })).toBeNull()
  })

  it('accepts the match on screen and moves to the next', async () => {
    const onClose = vi.fn()
    render(<MatchReviewModal matches={[match('a'), match('b')]} budgetId="b1" onClose={onClose} />)
    expect(screen.getByRole('button', { name: 'Previous match' })).toHaveClass('dialog-btn')
    await userEvent.click(screen.getByRole('button', { name: 'Accept link' }))
    expect(api.accept).toHaveBeenCalledWith('a')
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Next match' })).toBeNull())
    expect(onClose).not.toHaveBeenCalled()
  })

  it('keeps the last match separate and closes', async () => {
    const onClose = vi.fn()
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Keep separate' }))
    expect(api.reject).toHaveBeenCalledWith('a')
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
