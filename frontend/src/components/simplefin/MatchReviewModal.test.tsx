/**
 * Accept link and Keep separate sat inside the scrolling card, drawn in their
 * own button style, while Previous and Next were borderless text in the
 * footer — on a tall card the decision scrolled away from the queue controls.
 * The decision is the footer's now, in the shared dialog buttons.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { TransactionMatch } from '../../types'
import { makeTransaction } from '../../test-utils/factories'
import { MatchReviewModal } from './MatchReviewModal'

const api = vi.hoisted(() => ({
  accept: vi.fn((_: { matchId: string; keep?: unknown }) => Promise.resolve({})),
  /** What `useMergePreview` answers; a refusal when `previewError` is set. */
  preview: undefined as unknown,
  previewError: null as unknown,
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
vi.mock('../../api/accounts', () => ({ useAccounts: () => ({ data: [] }) }))
vi.mock('../../api/transactions', () => ({
  useTransaction: (id: string) => ({ data: api.txns[id], isLoading: false }),
  useMergePreview: (_budget: string, ids: unknown) =>
    api.previewError
      ? { data: undefined, isError: true, error: api.previewError }
      : { data: ids ? api.preview : undefined, isError: false, error: null },
  useTransactionSplits: () => ({ data: undefined }),
}))

/** The server's answer for a pair with nothing to choose between. */
const PREVIEW = {
  survivor_id: 'm-a',
  deleted_id: 's-a',
  date: '2026-09-01',
  amount: -24.6,
  replaced_amount: null,
  payee_id: null,
  category_id: null,
  memo: null,
  cleared: 'cleared',
  is_split: false,
  lines: [],
  has_bank_record: true,
  import_description: null,
  bank_posted_date: null,
  transfer: null,
  choices: {
    date: { source: 'm-a', choosable: false },
    payee: { source: null, choosable: false },
    category: { source: null, choosable: false },
    memo: { source: null, choosable: false },
  },
}

/** Fill both rows of a match, so the pair (and its preview) can be drawn. */
function seed(id: string) {
  api.txns[`s-${id}`] = makeTransaction({ id: `s-${id}`, has_sync_source: true })
  api.txns[`m-${id}`] = makeTransaction({ id: `m-${id}` })
}

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
  api.preview = PREVIEW
  api.previewError = null
  for (const id of ['a', 'b', 'c']) seed(id)
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
    expect(api.accept).toHaveBeenCalledWith({ matchId: 'a', keep: {} })
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Next match' })).toBeNull())
    expect(onClose).not.toHaveBeenCalled()
  })

  it('offers to keep the whole queue separate when the caller can do it', async () => {
    // A queue of false alarms had one way out: this dialog, a pair at a time.
    const onKeepAll = vi.fn()
    render(
      <MatchReviewModal
        matches={[match('a'), match('b'), match('c')]}
        budgetId="b1"
        onClose={vi.fn()}
        onKeepAllSeparate={onKeepAll}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: 'Keep all 3 separate' }))
    expect(onKeepAll).toHaveBeenCalledTimes(1)
    // The caller does it, in one change — not this dialog, pair by pair.
    expect(api.reject).not.toHaveBeenCalled()
  })

  it('has no keep-all for a single pair, or a queue it does not own', () => {
    const { unmount } = render(
      <MatchReviewModal
        matches={[match('a')]}
        budgetId="b1"
        onClose={vi.fn()}
        onKeepAllSeparate={vi.fn()}
      />
    )
    expect(screen.queryByRole('button', { name: /Keep all/ })).toBeNull()
    unmount()
    render(<MatchReviewModal matches={[match('a'), match('b')]} budgetId="b1" onClose={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Keep all/ })).toBeNull()
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

describe('the result of accepting', () => {
  // This dialog used to compose the merged row itself — a second
  // implementation of the merge that drew the entered row's date and category
  // whichever row the merge kept, and dropped a category it could not name.
  // It draws the server's preview now, through the same component as the
  // register's merge dialog.
  it('draws the served preview', () => {
    api.preview = { ...PREVIEW, memo: 'weekly shop — card purchase', cleared: 'reconciled' }
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={vi.fn()} />)
    const result = screen.getByRole('region', { name: 'After merging' })
    expect(result).toHaveTextContent('weekly shop — card purchase')
    expect(result).toHaveTextContent('reconciled')
    expect(result).toHaveTextContent('Bank record')
  })

  it('keeps the Category line for a category it cannot name', () => {
    // The old client-built preview dropped the line, showing a result with
    // no category while the accept kept it.
    api.preview = { ...PREVIEW, category_id: 'archived-gym' }
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={vi.fn()} />)
    expect(screen.getByRole('region', { name: 'After merging' })).toHaveTextContent('Category—')
  })

  it('sends the picks made on the cards with the accept', async () => {
    api.preview = {
      ...PREVIEW,
      choices: { ...PREVIEW.choices, date: { source: 'm-a', choosable: true } },
    }
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={vi.fn()} />)
    const bank = screen.getByRole('region', { name: 'From the bank' })
    await userEvent.click(within(bank).getByRole('radio', { name: 'Keep this date' }))
    await userEvent.click(screen.getByRole('button', { name: 'Accept link' }))
    expect(api.accept).toHaveBeenCalledWith({ matchId: 'a', keep: { date: 's-a' } })
  })

  it('starts the next pair from the defaults — picks belong to one pair', async () => {
    api.preview = {
      ...PREVIEW,
      choices: { ...PREVIEW.choices, date: { source: 'm-a', choosable: true } },
    }
    render(<MatchReviewModal matches={[match('a'), match('b')]} budgetId="b1" onClose={vi.fn()} />)
    const bank = () => screen.getByRole('region', { name: 'From the bank' })
    await userEvent.click(within(bank()).getByRole('radio', { name: 'Keep this date' }))
    await userEvent.click(screen.getByRole('button', { name: 'Next match' }))
    await userEvent.click(screen.getByRole('button', { name: 'Accept link' }))
    expect(api.accept).toHaveBeenCalledWith({ matchId: 'b', keep: {} })
  })

  it('says why, and offers no accept, when the server would refuse the merge', () => {
    api.previewError = {
      isAxiosError: true,
      response: { status: 400, data: { detail: 'Transactions must be in the same account' } },
    }
    render(<MatchReviewModal matches={[match('a')]} budgetId="b1" onClose={vi.fn()} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Transactions must be in the same account')
    expect(screen.getByRole('button', { name: 'Accept link' })).toBeDisabled()
    // Keeping them separate is still an answer.
    expect(screen.getByRole('button', { name: 'Keep separate' })).toBeEnabled()
  })
})
