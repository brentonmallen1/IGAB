/**
 * A scan row says where its transaction was filed.
 *
 * It used to show the model's reason and nothing about the category the
 * row was actually in, so an uncategorized row read the same as one filed
 * where the reason said. The row now names the filed category (served:
 * `transaction_category_id`), names the model's pick beside it when the two
 * differ, and lets a row still waiting for approval be re-filed without
 * approving it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { AIJob } from '../../../api/aiJobs'
import type { Category, CategoryGroup } from '../../../types'
import { makeCategory, makeCategoryGroup } from '../../../test-utils/factories'

const h = vi.hoisted(() => ({
  update: vi.fn(),
  approve: vi.fn(),
  waiting: [] as unknown[],
  history: [] as unknown[],
  categories: [] as unknown[],
  groups: [] as unknown[],
}))

vi.mock('../../../api/aiJobs', () => ({
  useAIJobs: (_budgetId: string, opts: { needsReview?: boolean }) => {
    const jobs = opts.needsReview ? h.waiting : h.history
    return { isLoading: false, data: { jobs, total_count: jobs.length } }
  },
  useAIJobCounts: () => ({ data: { active: 0, needsReview: h.waiting.length } }),
  useDeleteAIJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReprocessAIJob: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePlaceReceipt: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/transactions', () => ({
  useBulkApprove: () => ({ mutateAsync: h.approve, isPending: false }),
  useUpdateTransaction: () => ({ mutate: h.update, isPending: false }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: h.categories }),
  useCategoryGroups: () => ({ data: h.groups }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [{ id: 'acc-1', name: 'Harborstone Checking', on_budget: true, is_closed: false }],
  }),
}))
vi.mock('../../../hooks/useAccountMove', () => ({ useAccountMove: () => vi.fn() }))
vi.mock('../../../components/ai/CardEndingNotice', () => ({ CardEndingNotice: () => null }))
vi.mock('../../../hooks/useFormatters', () => ({
  useFormatters: () => ({
    formatMoney: (n: number) => `$${Math.abs(n).toFixed(2)}`,
    formatDateTime: () => 'Sep 20, 10:00',
  }),
}))

import { ScansTab } from './ScansTab'

const GROUPS: CategoryGroup[] = [
  makeCategoryGroup({ id: 'everyday', name: 'Everyday' }),
  makeCategoryGroup({ id: 'household', name: 'Household' }),
  makeCategoryGroup({ id: 'holidays', name: 'Holidays' }),
  makeCategoryGroup({ id: 'cards', name: 'Credit Card Payments' }),
]
const CATEGORIES: Category[] = [
  makeCategory({ id: 'groceries', name: 'Groceries', category_group_id: 'everyday' }),
  makeCategory({ id: 'dining', name: 'Dining Out', category_group_id: 'everyday' }),
  makeCategory({ id: 'gifts-home', name: 'Gifts', category_group_id: 'household' }),
  makeCategory({ id: 'gifts-hols', name: 'Gifts', category_group_id: 'holidays' }),
  makeCategory({
    id: 'sapphire',
    name: 'Sapphire Visa',
    category_group_id: 'cards',
    linked_account_id: 'acc-card',
    is_assignable: false,
    is_categorizable: false,
  }),
]

function scan(over: Partial<AIJob> = {}, pick: string | null = 'Groceries'): AIJob {
  return {
    id: 'job-1',
    budget_id: 'b1',
    kind: 'receipt',
    status: 'done',
    payload: { account_id: 'acc-1' },
    result: {
      draft: {
        payee: 'Corner Market',
        amount: '-12.50',
        date: '2026-09-20',
        category: pick,
        memo: null,
        confidence: 0.9,
      },
    },
    error: null,
    model: 'gemma4',
    attempts: 1,
    max_attempts: 3,
    transaction_id: 'txn-1',
    transaction_removed: false,
    needs_review: true,
    transaction_account_id: 'acc-1',
    transaction_category_id: 'groceries',
    transaction_is_split: false,
    card_ending_account_id: null,
    bank_match: null,
    attachment_id: null,
    created_at: '2026-09-20T10:00:00Z',
    started_at: null,
    finished_at: null,
    ...over,
  }
}

function renderTab({ waiting = [], history = [] }: { waiting?: AIJob[]; history?: AIJob[] }) {
  h.waiting = waiting
  h.history = history
  return render(
    <MemoryRouter>
      <ScansTab budgetId="b1" />
    </MemoryRouter>
  )
}

function row() {
  return screen.getByText('Corner Market').closest('.ai-activity__row') as HTMLElement
}

beforeEach(() => {
  h.update.mockClear()
  h.approve.mockClear()
  h.categories = CATEGORIES
  h.groups = GROUPS
})

describe('the category a scan is filed in', () => {
  it('names the category the row is in', () => {
    renderTab({ waiting: [scan()] })
    expect(within(row()).getByRole('button', { name: 'Groceries' })).toBeTruthy()
    expect(within(row()).queryByText(/AI suggested/)).toBeNull()
  })

  it('says what the AI suggested when the row is filed somewhere else', () => {
    renderTab({ waiting: [scan({ transaction_category_id: 'dining' })] })
    expect(within(row()).getByRole('button', { name: 'Dining Out' })).toBeTruthy()
    expect(within(row()).getByText('AI suggested Groceries')).toBeTruthy()
  })

  it('reads a group-qualified pick as the category it names', () => {
    // "Gifts" is in two groups, so the model's pick arrives qualified.
    renderTab({ waiting: [scan({ transaction_category_id: 'gifts-home' }, 'Gifts (Household)')] })
    expect(within(row()).queryByText(/AI suggested/)).toBeNull()
  })

  it('names the other same-named category as a different pick', () => {
    renderTab({ waiting: [scan({ transaction_category_id: 'gifts-home' }, 'Gifts (Holidays)')] })
    expect(within(row()).getByText('AI suggested Gifts (Holidays)')).toBeTruthy()
  })

  it('names the pick beside a row left uncategorized', () => {
    renderTab({ waiting: [scan({ transaction_category_id: null })] })
    expect(within(row()).getByRole('button', { name: 'Uncategorized' })).toBeTruthy()
    expect(within(row()).getByText('AI suggested Groceries')).toBeTruthy()
  })

  it('reads a split as Split, with no picker, and keeps its Edit link', () => {
    renderTab({
      waiting: [scan({ transaction_category_id: null, transaction_is_split: true })],
    })
    const r = within(row())
    expect(r.getByText('Split')).toBeTruthy()
    expect(r.queryByRole('button', { name: 'Split' })).toBeNull()
    expect(r.queryByRole('button', { name: 'Uncategorized' })).toBeNull()
    expect(r.getByRole('button', { name: /Edit/ })).toBeTruthy()
  })

  it('shows no category for a scan with no row yet', () => {
    renderTab({
      waiting: [
        scan({
          status: 'queued',
          transaction_id: null,
          transaction_account_id: null,
          transaction_category_id: null,
          needs_review: false,
        }),
      ],
    })
    expect(within(row()).queryByText('Uncategorized')).toBeNull()
    expect(within(row()).queryByText('Groceries')).toBeNull()
  })
})

describe('changing it while the scan waits', () => {
  it('offers the picker only while the row waits for approval', () => {
    renderTab({ history: [scan({ needs_review: false })] })
    fireEvent.click(screen.getByRole('button', { name: /History/ }))
    // Named, but read-only: an approved row is edited in its register.
    expect(within(row()).getByText('Groceries')).toBeTruthy()
    expect(within(row()).queryByRole('button', { name: 'Groceries' })).toBeNull()
  })

  it('files the row in the picked category and does not approve it', () => {
    renderTab({ waiting: [scan()] })
    fireEvent.click(within(row()).getByRole('button', { name: 'Groceries' }))
    expect(screen.getByRole('combobox', { name: 'File in category' })).toBeTruthy()
    // Combobox options select on mousedown.
    fireEvent.mouseDown(screen.getByText('Dining Out'))
    expect(h.update).toHaveBeenCalledTimes(1)
    expect(h.update.mock.calls[0][0]).toEqual({ id: 'txn-1', category_id: 'dining' })
    expect(h.approve).not.toHaveBeenCalled()
  })

  it('offers only what a row may be filed to', () => {
    renderTab({ waiting: [scan()] })
    fireEvent.click(within(row()).getByRole('button', { name: 'Groceries' }))
    // The card's envelope is in the category list and is never offered.
    expect(screen.queryByText('Sapphire Visa')).toBeNull()
    expect(screen.getByText('Dining Out')).toBeTruthy()
  })

  it('writes nothing when the current category is picked again', () => {
    // A no-op write would still land on the undo stack, in front of real work.
    renderTab({ waiting: [scan({ transaction_category_id: 'dining' })] })
    fireEvent.click(within(row()).getByRole('button', { name: 'Dining Out' }))
    const options = screen.getAllByText('Dining Out')
    fireEvent.mouseDown(options[options.length - 1])
    expect(h.update).not.toHaveBeenCalled()
  })
})
