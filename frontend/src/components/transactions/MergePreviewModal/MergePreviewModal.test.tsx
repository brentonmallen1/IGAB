/**
 * The merge preview's refusal slot.
 *
 * The register cannot rule out every refusal on its own — which row may
 * survive is the server's decision — so a refusal will reach this modal.
 * It used to be swallowed: `mutateAsync` was awaited with no catch, so a
 * duplicate of a reconciled row that the server would not merge left the
 * Merge button doing nothing at all, with no message anywhere.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MergePreviewModal } from './MergePreviewModal'
import type { Transaction } from '../../../types'

function txn(overrides: Partial<Transaction> = {}): Transaction {
  return {
    id: 't1',
    account_id: 'a1',
    date: '2026-09-01',
    amount: -24.6,
    payee_id: 'p1',
    category_id: null,
    memo: null,
    cleared: 'cleared',
    is_split: false,
    transfer_id: null,
    parent_transaction_id: null,
    sync_id: 'TRN-b1a0',
    ...overrides,
  } as unknown as Transaction
}

function open(error: string | null = null) {
  const onConfirm = vi.fn()
  render(
    <MergePreviewModal
      transactions={[txn(), txn({ id: 't2', cleared: 'reconciled', sync_id: 'TRN-c6ba' })]}
      payeeMap={new Map([['p1', 'Hobby Lobby']])}
      categoryMap={new Map()}
      onConfirm={onConfirm}
      onCancel={vi.fn()}
      isPending={false}
      error={error}
    />
  )
  return { onConfirm }
}

describe('MergePreviewModal', () => {
  it('shows the server’s refusal instead of leaving the button silent', () => {
    open('Both transactions are linked to different bank transactions')
    expect(
      screen.getByText('Both transactions are linked to different bank transactions')
    ).toBeTruthy()
  })

  it('says nothing when there is nothing to say', () => {
    open()
    expect(screen.queryByText(/could not be merged/)).toBeNull()
  })

  it('still confirms — the error slot does not block a retry', () => {
    const { onConfirm } = open('Something the server refused')
    fireEvent.click(screen.getByText('Merge'))
    expect(onConfirm).toHaveBeenCalled()
  })
})
