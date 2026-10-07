/**
 * The adjustment amount crosses the API boundary, where `Money` rejects
 * anything past four decimal places. Computed as a float, the difference
 * between two ordinary statement balances routinely lands on twelve —
 * `100.10 - 7865.90` is `-7765.799999999999` — and every one of those posts
 * came back 422, so "Create adjustment" was broken for all but the amounts
 * that happen to be exact in binary.
 *
 * These cases are the real pairs that failed; they are here so the cents
 * arithmetic cannot quietly become float arithmetic again.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReconcileStatusBar } from './ReconcileStatusBar'

const createAdjustment = vi.hoisted(() => vi.fn((_amount: number) => Promise.resolve({ id: 't1' })))
const finishReconciliation = vi.hoisted(() =>
  vi.fn((_params: { statement_balance: number; adjustment_transaction_id: string | null }) =>
    Promise.resolve({})
  )
)
let clearedBalance = 0
let inReviewCount = 0

vi.mock('../../api/reconciliation', () => ({
  useReconciliationStatus: () => ({
    data: {
      cleared_balance: clearedBalance,
      uncleared_count: 0,
      pending_count: 0,
      in_review_count: inReviewCount,
    },
  }),
  useCreateAdjustment: () => ({ mutateAsync: createAdjustment, isPending: false }),
  useFinishReconciliation: () => ({ mutateAsync: finishReconciliation, isPending: false }),
}))

let statementBalance = 0
const cancelReconciliation = vi.hoisted(() => vi.fn())
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({
    reconcileStatementBalance: statementBalance,
    reconcileAdjustmentTxnId: null,
    setReconcileAdjustmentTxnId: vi.fn(),
    cancelReconciliation,
    selectedTransactionIds: new Set<string>(),
  }),
}))

const onReviewDuplicates = vi.fn()

function renderBar() {
  render(<ReconcileStatusBar accountId="a1" onReviewDuplicates={onReviewDuplicates} />)
}

/** Decimal places in the number as it would be serialized into the request. */
function decimalPlaces(amount: number): number {
  return (String(amount).split('.')[1] ?? '').length
}

beforeEach(() => {
  createAdjustment.mockClear()
  finishReconciliation.mockClear()
  cancelReconciliation.mockClear()
  onReviewDuplicates.mockClear()
  inReviewCount = 0
})

describe('ReconcileStatusBar', () => {
  it.each([
    [100.1, 7865.9],
    [1234.56, 999.99],
    [-55.68, 144.27],
    [0.1, 0.3],
  ])('posts a cent-exact adjustment for statement %s vs cleared %s', async (stmt, cleared) => {
    statementBalance = stmt
    clearedBalance = cleared
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: /create adjustment/i }))

    expect(createAdjustment).toHaveBeenCalledTimes(1)
    const posted = createAdjustment.mock.calls[0][0]
    expect(decimalPlaces(posted)).toBeLessThanOrEqual(2)
    // and it is still the right amount, to the cent
    expect(Math.round(posted * 100)).toBe(Math.round(stmt * 100) - Math.round(cleared * 100))
  })

  it('calls a difference of exactly zero balanced, without a float epsilon', async () => {
    statementBalance = 7865.9
    clearedBalance = 7865.9
    renderBar()

    expect(screen.getByText('Balanced')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /finish reconciling/i }))
    const posted = finishReconciliation.mock.calls[0][0]
    expect(decimalPlaces(posted.statement_balance)).toBeLessThanOrEqual(2)
  })

  it('a sub-cent gap is not balanced — the bank disagrees by a cent', () => {
    statementBalance = 7865.91
    clearedBalance = 7865.9
    renderBar()

    expect(screen.queryByText('Balanced')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create adjustment/i })).toBeInTheDocument()
  })
})

/**
 * While a duplicate review is open the cleared balance counts the queued
 * rows twice, so "Balanced" against the bank is balanced against a wrong
 * number. Finishing there wrote an adjustment the merge then made
 * permanently short; the server refuses with a 409, and the bar says so
 * before the click and shows the refusal if one slips through.
 */
describe('ReconcileStatusBar with duplicates waiting in review', () => {
  const REFUSAL =
    '1 possible duplicate on this account is waiting in review — settle it first, or the reconciliation will count it twice.'

  it('holds Finish while a duplicate is in review, and offers the review', async () => {
    statementBalance = 935.8
    clearedBalance = 935.8
    inReviewCount = 1
    renderBar()

    expect(screen.getByRole('button', { name: /finish reconciling/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Review 1 possible duplicate' }))
    expect(onReviewDuplicates).toHaveBeenCalledTimes(1)
    expect(finishReconciliation).not.toHaveBeenCalled()
  })

  it('counts several in the plural', () => {
    statementBalance = 935.8
    clearedBalance = 935.8
    inReviewCount = 2
    renderBar()
    expect(screen.getByRole('button', { name: 'Review 2 possible duplicates' })).toBeInTheDocument()
  })

  it('holds Create adjustment too — the difference is the doubled money', () => {
    statementBalance = 935.8
    clearedBalance = 871.6
    inReviewCount = 1
    renderBar()
    expect(screen.getByRole('button', { name: /create adjustment/i })).toBeDisabled()
  })

  it('enables Finish once nothing is waiting', () => {
    statementBalance = 935.8
    clearedBalance = 935.8
    inReviewCount = 0
    renderBar()

    expect(screen.getByRole('button', { name: /finish reconciling/i })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /possible duplicate/ })).not.toBeInTheDocument()
  })

  it('shows the server refusal and stays open when finish is refused', async () => {
    // A sync queued a pair between the last poll and the click.
    statementBalance = 935.8
    clearedBalance = 935.8
    inReviewCount = 0
    finishReconciliation.mockRejectedValueOnce({
      response: { status: 409, data: { detail: REFUSAL } },
    })
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: /finish reconciling/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(REFUSAL)
    expect(cancelReconciliation).not.toHaveBeenCalled()
  })

  it('shows the server refusal when the adjustment is refused', async () => {
    statementBalance = 935.8
    clearedBalance = 871.6
    inReviewCount = 0
    createAdjustment.mockRejectedValueOnce({
      response: { status: 409, data: { detail: REFUSAL } },
    })
    renderBar()

    await userEvent.click(screen.getByRole('button', { name: /create adjustment/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(REFUSAL)
  })
})
