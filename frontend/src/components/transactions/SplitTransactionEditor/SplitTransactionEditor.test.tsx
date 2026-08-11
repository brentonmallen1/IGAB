/**
 * Money-critical tests for the inline split editor: integer-cents remainder
 * math (float sums must not reject valid splits), save gating, and the
 * create-then-delete replacement payload that keeps totals intact.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const createMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({ id: 'new-split' })))
const deleteMutate = vi.hoisted(() => vi.fn(() => Promise.resolve()))

vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: createMutate, isPending: false }),
  useDeleteTransaction: () => ({ mutateAsync: deleteMutate, isPending: false }),
}))
// The real store is persist-backed; tests only need the current budget id
vi.mock('../../../stores/appStore', () => ({
  useAppStore: (selector: (s: { currentBudgetId: string }) => unknown) =>
    selector({ currentBudgetId: 'budget-1' }),
}))

import { SplitTransactionEditor } from './SplitTransactionEditor'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import type { Category, CategoryGroup, Transaction } from '../../../types'

const TXN = {
  id: 'txn-1',
  account_id: 'acc-1',
  date: '2026-08-01',
  amount: -10,
  payee_id: null,
  memo: null,
  cleared: 'uncleared',
} as unknown as Transaction

const GROUPS = [{ id: 'g1', name: 'Everyday' }] as unknown as CategoryGroup[]
const CATEGORIES = [
  { id: 'c1', category_group_id: 'g1', name: 'Groceries' },
  { id: 'c2', category_group_id: 'g1', name: 'Fun' },
] as unknown as Category[]

function startSplit(totalAmount: number, splits: { amount: string; categoryId: string | null }[]) {
  useTransactionEditStore.getState().startSplitEditing(
    'txn-1',
    totalAmount,
    splits.map((s, i) => ({ tempId: `s${i}`, amount: s.amount, categoryId: s.categoryId, memo: '' }))
  )
}

function renderEditor() {
  return render(
    <SplitTransactionEditor transaction={TXN} categories={CATEGORIES} categoryGroups={GROUPS} />
  )
}

function saveButton() {
  return screen.getByRole('button', { name: 'Save Split' })
}

describe('SplitTransactionEditor cents math', () => {
  beforeEach(() => {
    createMutate.mockClear()
    deleteMutate.mockClear()
    useTransactionEditStore.getState().stopSplitEditing()
  })

  it('computes the remainder in integer cents', () => {
    startSplit(-10, [
      { amount: '3.33', categoryId: 'c1' },
      { amount: '3.33', categoryId: 'c2' },
    ])
    renderEditor()
    expect(screen.getByText('Remaining: $3.34')).toBeInTheDocument()
    expect(saveButton()).toBeDisabled()
  })

  it('accepts splits that float addition would reject (0.10 problems)', () => {
    // 1.10 !== 1.00 + 0.10 in binary floats; integer cents must say "done"
    startSplit(-1.1, [
      { amount: '1.00', categoryId: 'c1' },
      { amount: '0.10', categoryId: 'c2' },
    ])
    renderEditor()
    expect(screen.getByText('Fully assigned')).toBeInTheDocument()
    expect(saveButton()).toBeEnabled()
  })

  it('blocks saving when a fully-assigned split is missing a category', () => {
    startSplit(-10, [
      { amount: '6.00', categoryId: 'c1' },
      { amount: '4.00', categoryId: null },
    ])
    renderEditor()
    expect(screen.getByText('Fully assigned')).toBeInTheDocument()
    expect(saveButton()).toBeDisabled()
  })

  it('updates the remainder as amounts are typed', () => {
    startSplit(-10, [
      { amount: '', categoryId: 'c1' },
      { amount: '', categoryId: 'c2' },
    ])
    renderEditor()
    const [first, second] = screen.getAllByPlaceholderText('0.00')
    fireEvent.change(first, { target: { value: '7.25' } })
    expect(screen.getByText('Remaining: $2.75')).toBeInTheDocument()
    fireEvent.change(second, { target: { value: '2.75' } })
    expect(screen.getByText('Fully assigned')).toBeInTheDocument()
  })

  it('saves the split with signed line amounts, then deletes the original row', async () => {
    startSplit(-25, [
      { amount: '10.00', categoryId: 'c1' },
      { amount: '15.00', categoryId: 'c2' },
    ])
    renderEditor()
    fireEvent.click(saveButton())

    await waitFor(() => expect(deleteMutate).toHaveBeenCalled())
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        account_id: 'acc-1',
        date: '2026-08-01',
        amount: -25,
        splits: [
          expect.objectContaining({ amount: -10, category_id: 'c1' }),
          expect.objectContaining({ amount: -15, category_id: 'c2' }),
        ],
      })
    )
    expect(deleteMutate).toHaveBeenCalledWith({ id: 'txn-1', accountId: 'acc-1' })
    // The editor closes itself: both rows surviving would double-count
    expect(useTransactionEditStore.getState().splitEditing).toBeNull()
  })
})
