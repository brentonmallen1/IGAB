/**
 * The register's "show split lines" toggle, end to end through the table:
 * off asks the server for nothing, on asks once for every split on the page
 * and draws the lines under their row, and an open split editor replaces its
 * row's lines rather than stacking under them.
 *
 * The network is the mocked `apiClient`, and `useSplitLinesFor` is the real
 * hook — "no request" is asserted on the wire, not on a stubbed hook.
 */
import type { ReactNode } from 'react'
import { act, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeTransaction } from '../../../test-utils/factories'
import type { Transaction } from '../../../types'

const h = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  rows: [] as unknown[],
}))

vi.mock('../../../api/client', () => ({
  apiClient: { get: h.get, post: h.post },
  apiErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

// Every row in hand at once: jsdom has no layout, so the real virtualizer
// would draw no rows at all.
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () => Array.from({ length: count }, (_, i) => ({ index: i, start: i * 34 })),
    getTotalSize: () => count * 34,
    measureElement: () => {},
    scrollToIndex: () => {},
  }),
}))

vi.mock('../../../api/transactions', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../../api/transactions')>()
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false })
  const page = () => ({
    data: { pages: [h.rows] },
    dataUpdatedAt: 1,
    isLoading: false,
    isFetching: false,
    isFetchingNextPage: false,
    hasNextPage: false,
    fetchNextPage: vi.fn(),
  })
  return {
    ...real,
    useInfiniteTransactions: page,
    useInfiniteBudgetTransactions: page,
    usePayees: () => ({ data: [] }),
    useBulkUpdateCleared: idle,
    useBulkCategorize: idle,
    useBulkDeleteTransactions: idle,
    useCreateTransaction: idle,
    useBulkApprove: idle,
    useMergeTransactions: idle,
    usePendingReviewCountForAccount: () => ({ data: { total: 0 } }),
    usePendingReviewCount: () => ({ data: { total: 0 } }),
  }
})
vi.mock('../../../api/payees', () => ({
  usePayees: () => ({ data: [] }),
  useCreatePayee: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../../../api/attachments', () => ({
  useCheckAttachments: () => ({ data: {} }),
  confirmDeleteTransaction: vi.fn(),
}))
vi.mock('../../../api/aiJobs', () => ({ useAIJobForTransaction: () => ({ data: null }) }))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      { id: 'cat-groceries', name: 'Groceries', category_group_id: 'g1' },
      { id: 'cat-household', name: 'Household', category_group_id: 'g1' },
    ],
  }),
  useCategoryGroups: () => ({ data: [] }),
  useCreateCategory: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [{ id: 'acc-1', name: 'Checking', on_budget: true, is_closed: false }],
  }),
}))
vi.mock('../../../api/scheduledTransactions', () => ({
  useScheduledTransactionsByAccount: () => ({ data: [] }),
  useScheduledTransactions: () => ({ data: [] }),
  useEnterScheduledTransaction: () => ({ mutate: vi.fn(), isPending: false }),
  useSkipScheduledTransaction: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/simplefin', () => ({
  usePendingMatchesForAccount: () => ({ data: [] }),
  useRejectMatch: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../TransactionRow/RowAttachmentButton', () => ({ RowAttachmentButton: () => null }))
vi.mock('../../simplefin/BankRecordIcon', () => ({ BankRecordIcon: () => null }))

import { TransactionTable } from './TransactionTable'
import { useSplitLinesFor } from '../../../api/transactions'
import { useUIStore } from '../../../stores/uiStore'
import { useAppStore } from '../../../stores/appStore'
import { useTransactionEditStore } from '../../../stores/transactionEditStore'

const split = makeTransaction({
  id: 'split-1',
  account_id: 'acc-1',
  amount: -100,
  is_split: true,
  cleared: 'cleared',
})
const plain = makeTransaction({
  id: 'plain-1',
  account_id: 'acc-1',
  amount: -12,
  category_id: 'cat-groceries',
  cleared: 'cleared',
})
const lines: Transaction[] = [
  makeTransaction({
    id: 'line-1',
    amount: -60,
    category_id: 'cat-groceries',
    memo: 'weekly shop',
    parent_transaction_id: 'split-1',
  }),
  makeTransaction({
    id: 'line-2',
    amount: -40,
    category_id: 'cat-household',
    parent_transaction_id: 'split-1',
  }),
]

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TransactionTable accountId="acc-1" budgetId="budget-1" />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const splitLineCalls = () =>
  h.post.mock.calls.filter(([url]) => String(url).endsWith('/transactions/split-lines'))

beforeEach(() => {
  h.rows = [split, plain]
  h.post.mockReset()
  h.get.mockReset()
  h.post.mockImplementation(async (url: string) =>
    String(url).endsWith('/transactions/split-lines')
      ? { data: { 'split-1': lines } }
      : { data: {} }
  )
  // The inline split editor reads one split's lines.
  h.get.mockImplementation(async (url: string) => ({
    data: String(url) === '/transactions/split-1/splits' ? lines : [],
  }))
  useAppStore.setState({ currentBudgetId: 'budget-1' })
  useUIStore.setState({ showSplitLines: false })
  useTransactionEditStore.getState().stopSplitEditing()
})

afterEach(() => {
  useUIStore.setState({ showSplitLines: false })
  useTransactionEditStore.getState().stopSplitEditing()
})

describe('register split lines', () => {
  it('asks for nothing and draws no lines while the toggle is off', async () => {
    renderTable()
    expect(await screen.findByText('Split Transaction')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show split lines' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
    expect(splitLineCalls()).toHaveLength(0)
    expect(screen.queryByRole('group', { name: 'Split lines' })).not.toBeInTheDocument()
  })

  it('asks once for the splits on the page and draws their lines under the row', async () => {
    renderTable()
    act(() => {
      screen.getByRole('button', { name: 'Show split lines' }).click()
    })
    expect(useUIStore.getState().showSplitLines).toBe(true)

    const group = await screen.findByRole('group', { name: 'Split lines' })
    expect(within(group).getByText('Groceries')).toBeInTheDocument()
    expect(within(group).getByText('Household')).toBeInTheDocument()
    expect(within(group).getByText('weekly shop')).toBeInTheDocument()

    // One request, naming only the split parents — never the plain row.
    expect(splitLineCalls()).toHaveLength(1)
    expect(splitLineCalls()[0]).toEqual([
      '/budget-1/transactions/split-lines',
      { parent_ids: ['split-1'] },
    ])

    // Drawn under its own row, not somewhere else in the register.
    const parentRow = document.querySelector('[data-txn-id="split-1"]')!
    expect(parentRow.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const plainRow = document.querySelector('[data-txn-id="plain-1"]')!
    expect(plainRow.parentElement?.querySelector('.split-lines')).toBeNull()
  })

  it('asks nothing when the page holds no split', async () => {
    h.rows = [plain]
    useUIStore.setState({ showSplitLines: true })
    renderTable()
    expect(await screen.findByText('Groceries')).toBeInTheDocument()
    expect(splitLineCalls()).toHaveLength(0)
  })

  it("hides a split's lines while its editor is open, and draws them again once it closes", async () => {
    useUIStore.setState({ showSplitLines: true })
    renderTable()
    await screen.findByRole('group', { name: 'Split lines' })

    act(() => {
      useTransactionEditStore.getState().startSplitEditing('split-1', -100, true)
    })
    await waitFor(() =>
      expect(screen.queryByRole('group', { name: 'Split lines' })).not.toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: 'Cancel split' })).toBeInTheDocument()

    act(() => {
      useTransactionEditStore.getState().stopSplitEditing()
    })
    expect(await screen.findByRole('group', { name: 'Split lines' })).toBeInTheDocument()
  })

  it('opens the split editor when a line is clicked', async () => {
    useUIStore.setState({ showSplitLines: true })
    renderTable()
    const group = await screen.findByRole('group', { name: 'Split lines' })
    act(() => {
      within(group).getByText('Household').click()
    })
    expect(useTransactionEditStore.getState().splitEditing?.transactionId).toBe('split-1')
  })
})

describe('useSplitLinesFor', () => {
  function wrapper({ children }: { children: ReactNode }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
  const settle = () => new Promise((r) => setTimeout(r, 20))

  it('keeps one key whatever order the page lists its splits in', async () => {
    const { rerender } = renderHook(
      ({ ids }: { ids: string[] }) => useSplitLinesFor('budget-1', ids, true, 1),
      { wrapper, initialProps: { ids: ['split-b', 'split-a'] } }
    )
    await waitFor(() => expect(splitLineCalls()).toHaveLength(1))
    expect(splitLineCalls()[0][1]).toEqual({ parent_ids: ['split-a', 'split-b'] })
    // A re-sorted register is the same question; it must not ask again.
    rerender({ ids: ['split-a', 'split-b'] })
    await settle()
    expect(splitLineCalls()).toHaveLength(1)
  })

  it('asks again whenever the register rows it hangs under are refetched', async () => {
    // Every refresh path — a split save, an edit, a delete, undo, a sync —
    // refetches the register. The lines follow it, rather than each of those
    // paths having to list them.
    const { rerender } = renderHook(
      ({ at }: { at: number }) => useSplitLinesFor('budget-1', ['split-1'], true, at),
      { wrapper, initialProps: { at: 1 } }
    )
    await waitFor(() => expect(splitLineCalls()).toHaveLength(1))
    rerender({ at: 2 })
    await waitFor(() => expect(splitLineCalls()).toHaveLength(2))
  })

  it('asks nothing while switched off', async () => {
    renderHook(() => useSplitLinesFor('budget-1', ['split-1'], false, 1), { wrapper })
    await settle()
    expect(splitLineCalls()).toHaveLength(0)
  })
})
