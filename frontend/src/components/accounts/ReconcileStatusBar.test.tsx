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

const createAdjustment = vi.hoisted(() =>
  vi.fn((_amount: number) => Promise.resolve({ id: 't1' }))
)
const finishReconciliation = vi.hoisted(() =>
  vi.fn((_params: { statement_balance: number; adjustment_transaction_id: string | null }) =>
    Promise.resolve({})
  )
)
let clearedBalance = 0

vi.mock('../../api/reconciliation', () => ({
  useReconciliationStatus: () => ({
    data: { cleared_balance: clearedBalance, uncleared_count: 0, pending_count: 0 },
  }),
  useCreateAdjustment: () => ({ mutateAsync: createAdjustment, isPending: false }),
  useFinishReconciliation: () => ({ mutateAsync: finishReconciliation, isPending: false }),
}))

let statementBalance = 0
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({
    reconcileStatementBalance: statementBalance,
    reconcileAdjustmentTxnId: null,
    setReconcileAdjustmentTxnId: vi.fn(),
    cancelReconciliation: vi.fn(),
    selectedTransactionIds: new Set<string>(),
  }),
}))

/** Decimal places in the number as it would be serialized into the request. */
function decimalPlaces(amount: number): number {
  return (String(amount).split('.')[1] ?? '').length
}

beforeEach(() => {
  createAdjustment.mockClear()
  finishReconciliation.mockClear()
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
    render(<ReconcileStatusBar accountId="a1" />)

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
    render(<ReconcileStatusBar accountId="a1" />)

    expect(screen.getByText('Balanced')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /finish reconciling/i }))
    const posted = finishReconciliation.mock.calls[0][0]
    expect(decimalPlaces(posted.statement_balance)).toBeLessThanOrEqual(2)
  })

  it('a sub-cent gap is not balanced — the bank disagrees by a cent', () => {
    statementBalance = 7865.91
    clearedBalance = 7865.9
    render(<ReconcileStatusBar accountId="a1" />)

    expect(screen.queryByText('Balanced')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create adjustment/i })).toBeInTheDocument()
  })
})
