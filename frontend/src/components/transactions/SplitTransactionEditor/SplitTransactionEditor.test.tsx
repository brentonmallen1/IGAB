/**
 * The inline split editor edits a split's lines in place. Its lines come from
 * the server — never from the loaded register page, which holds parent rows
 * only. Before this, an existing split opened with two empty lines and a
 * save replaced the real ones with them.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const replaceMutate = vi.hoisted(() =>
  vi.fn((_payload: Record<string, unknown>) => Promise.resolve({ id: 't1', lines: [] }))
)
const convertMutate = vi.hoisted(() =>
  vi.fn((_payload: Record<string, unknown>) => Promise.resolve({}))
)
let serverLines: unknown[] | undefined

vi.mock('../../../api/transactions', () => ({
  useTransactionSplits: () => ({ data: serverLines }),
  useConvertToSplit: () => ({ mutateAsync: convertMutate, isPending: false }),
  useReplaceSplits: () => ({ mutateAsync: replaceMutate, isPending: false }),
}))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))

import { SplitTransactionEditor } from './SplitTransactionEditor'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'
import { useAppStore } from '../../../stores/appStore'
import type { Transaction } from '../../../types'

const PARENT = {
  id: 't1',
  account_id: 'a1',
  amount: -100,
  is_split: true,
  cleared: 'uncleared',
} as Transaction
const FLAT = {
  id: 't2',
  account_id: 'a1',
  amount: -100,
  is_split: false,
  cleared: 'uncleared',
} as Transaction

function renderEditor(txn: Transaction) {
  const qc = new QueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <SplitTransactionEditor transaction={txn} categories={[]} categoryGroups={[]} />
    </QueryClientProvider>
  )
}

const amountInputs = () => screen.getAllByPlaceholderText('0.00') as HTMLInputElement[]

describe('SplitTransactionEditor', () => {
  beforeEach(() => {
    replaceMutate.mockClear()
    convertMutate.mockClear()
    useAppStore.setState({ currentBudgetId: 'b1' })
    useTransactionEditStore.getState().stopSplitEditing()
  })

  it('opens populated from the server lines even when the page holds none', async () => {
    serverLines = [
      { id: 'l1', amount: -60, category_id: 'cat-1', memo: 'food' },
      { id: 'l2', amount: -40, category_id: 'cat-2', memo: null },
    ]
    useTransactionEditStore.getState().startSplitEditing(PARENT.id, -100, true)
    renderEditor(PARENT)

    await waitFor(() => expect(amountInputs()).toHaveLength(2))
    expect(amountInputs().map((i) => i.value)).toEqual(['60', '40'])
    expect(screen.getByText('Fully assigned')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Save Split'))
    await waitFor(() => expect(replaceMutate).toHaveBeenCalledTimes(1))
    expect(replaceMutate.mock.calls[0][0]).toEqual({
      id: 't1',
      splits: [
        { id: 'l1', amount: -60, category_id: 'cat-1', memo: 'food' },
        { id: 'l2', amount: -40, category_id: 'cat-2', memo: undefined },
      ],
    })
    expect(convertMutate).not.toHaveBeenCalled()
  })

  it('cannot save while an existing split’s lines are still loading', () => {
    serverLines = undefined
    useTransactionEditStore.getState().startSplitEditing(PARENT.id, -100, true)
    renderEditor(PARENT)

    expect(screen.getByRole('status')).toHaveTextContent('Loading lines')
    expect(screen.getByText('Save Split')).toBeDisabled()
  })

  it('a new split converts the row in place rather than replacing it', async () => {
    serverLines = undefined
    useTransactionEditStore.getState().startSplitEditing(FLAT.id, -100, false)
    renderEditor(FLAT)

    // Amounts through the inputs; categories through the store (the
    // combobox is its own component, and every line needs one to be valid).
    const [first, second] = amountInputs()
    fireEvent.change(first, { target: { value: '60' } })
    fireEvent.change(second, { target: { value: '40' } })
    const { splitEditing, updateSplit } = useTransactionEditStore.getState()
    updateSplit(splitEditing!.splits[0].tempId, { categoryId: 'cat-1' })
    updateSplit(splitEditing!.splits[1].tempId, { categoryId: 'cat-2' })
    await waitFor(() => expect(screen.getByText('Save Split')).not.toBeDisabled())

    fireEvent.click(screen.getByText('Save Split'))
    await waitFor(() => expect(convertMutate).toHaveBeenCalledTimes(1))
    expect(convertMutate.mock.calls[0][0]).toMatchObject({ id: 't2' })
    expect(
      (convertMutate.mock.calls[0][0] as { splits: { id?: string }[] }).splits.every(
        (s) => s.id === undefined
      )
    ).toBe(true)
    expect(replaceMutate).not.toHaveBeenCalled()
  })
})
