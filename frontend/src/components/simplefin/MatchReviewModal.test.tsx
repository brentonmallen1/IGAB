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
import { makeTransaction } from '../../test-utils/factories'
import { MatchReviewModal } from './MatchReviewModal'

const api = vi.hoisted(() => ({
  accept: vi.fn((_: string) => Promise.resolve({})),
  reject: vi.fn((_: string) => Promise.resolve({})),
  /** Rows `useTransaction` answers with; empty unless a test fills it. */
  txns: {} as Record<string, unknown>,
}))
vi.mock('../../api/simplefin', () => ({
  useAcceptMatch: () => ({ mutateAsync: api.accept, isPending: false }),
  useRejectMatch: () => ({ mutateAsync: api.reject, isPending: false }),
}))
vi.mock('../../api/payees', () => ({ usePayees: () => ({ data: [] }) }))
vi.mock('../../api/categories', () => ({
  useCategories: () => ({ data: [] }),
  useCategoryGroups: () => ({ data: [] }),
}))
vi.mock('../../api/transactions', () => ({
  useTransaction: (id: string) => ({ data: api.txns[id], isLoading: false }),
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
  api.txns = {}
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

  it('shows a refused accept instead of doing nothing, and stays on the match', async () => {
    const onClose = vi.fn()
    api.accept.mockImplementationOnce(() =>
      Promise.reject({
        isAxiosError: true,
        response: { status: 400, data: { detail: 'Transactions must be in the same account' } },
      })
    )
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Accept link' }))
    expect(await screen.findByText('Transactions must be in the same account')).toBeTruthy()
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('the Category line', () => {
  it('MatchReviewModal: the merged preview keeps a category it cannot name', () => {
    // The detail columns drew "—" for it; the merged preview dropped the line,
    // previewing a result with no category while the accept keeps the
    // manual row's. Here the category list has nothing in it at all.
    api.txns = {
      's-a': makeTransaction({ id: 's-a', category_id: null, has_sync_source: true }),
      'm-a': makeTransaction({ id: 'm-a', category_id: 'archived-gym' }),
    }
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={vi.fn()} />)
    const merged = document.querySelector('.match-modal__merged')!
    const keys = [...merged.querySelectorAll('.match-modal__txn-key')].map((k) => k.textContent)
    expect(keys).toContain('Category')
    expect(merged.textContent).toContain('—')
  })
})
