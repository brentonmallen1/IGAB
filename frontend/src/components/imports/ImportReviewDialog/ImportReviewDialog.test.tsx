/**
 * The review shows what the import decided and changes nothing until asked.
 *
 * The behaviour worth pinning is the restraint: a suggestion sits unchecked,
 * accepting one writes nothing on its own, and Done sends exactly the
 * categories that moved — in one request, because each change is a
 * classification override and half a review applied is worse than none.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { ImportReviewDialog } from './ImportReviewDialog'
import type { YnabImportResult } from '../../../api/imports'

const bulkSet = vi.fn().mockResolvedValue(undefined)
const markReviewed = vi.fn().mockResolvedValue(undefined)

const categories = [
  {
    id: 'prime',
    category_group_id: 'g1',
    name: 'Amazon Prime',
    is_hidden: false,
    tags: [{ id: 't-lte', name: 'Long-term expense', color_slot: 'teal' }],
  },
  { id: 'rent', category_group_id: 'g1', name: 'Rent', is_hidden: false, tags: [] },
  { id: 'income', category_group_id: 'sys', name: 'Inflow', is_hidden: false, tags: [] },
]
const groups = [
  { id: 'g1', name: 'Everyday', is_system: false },
  { id: 'sys', name: 'Income', is_system: true },
]
const tags = [
  { id: 't-lte', name: 'Long-term expense', system_key: 'long_term_expense', color_slot: 'teal' },
  { id: 't-sub', name: 'Subscription', system_key: 'subscription', color_slot: 'purple' },
  { id: 't-ess', name: 'Essential', system_key: 'essential', color_slot: 'blue' },
]
const suggestions = [
  { category_id: 'prime', system_key: 'subscription', matched_on: 'Amazon Prime', applied_on_import: false },
  { category_id: 'rent', system_key: 'essential', matched_on: 'Rent', applied_on_import: false },
]

vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: categories }),
  useCategoryGroups: () => ({ data: groups }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccountHygiene: () => ({ data: { findings: [], clean: true } }),
  useRepairTransfers: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/tags', () => ({
  useTags: () => ({ data: tags }),
  useTagSuggestions: () => ({ data: suggestions }),
  useBulkSetCategoryTags: () => ({ mutateAsync: bulkSet, isPending: false }),
}))
vi.mock('../../../api/imports', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useMarkImportReviewed: () => ({ mutateAsync: markReviewed, isPending: false }),
}))
vi.mock('../../../hooks/useFocusTrap', () => ({ useFocusTrap: () => ({ current: null }) }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

function summary(over: Partial<YnabImportResult> = {}): YnabImportResult {
  return {
    accounts: 3,
    category_groups: 2,
    categories: 3,
    transactions: 412,
    skipped: 0,
    assignments: 40,
    accounts_skipped: 0,
    accounts_closed: 0,
    transactions_excluded: 0,
    transfer_legs_unpaired: 0,
    transfer_legs_in_splits: 0,
    categories_tagged: 1,
    tagged_categories: [
      { category_id: 'prime', system_key: 'long_term_expense', matched_on: 'Long Term Expenses' },
    ],
    credit_card_payment_assignments_skipped: 0,
    credit_card_payment_reserves_skipped: '0',
    parity: null,
    errors: [],
    ...over,
  }
}

function open(over: Partial<YnabImportResult> | null = {}) {
  return render(
    <MemoryRouter>
      <ImportReviewDialog
        budgetId="b1"
        summary={over === null ? null : summary(over)}
        onClose={() => {}}
      />
    </MemoryRouter>
  )
}

beforeEach(() => {
  bulkSet.mockClear()
  markReviewed.mockClear()
})

describe('the report', () => {
  it('opens on what arrived', () => {
    open()
    expect(screen.getByText('412')).toBeInTheDocument()
    expect(screen.getByText('transactions')).toBeInTheDocument()
  })

  it('shows every error, not just the first', async () => {
    open({ errors: ['row 3 bad amount', 'row 9 bad date', 'row 40 bad payee'] })
    expect(screen.getByText('row 3 bad amount')).toBeInTheDocument()
    expect(screen.getByText('row 40 bad payee')).toBeInTheDocument()
  })

  it('is skipped for a budget with no stored summary', () => {
    open(null)
    // Straight to what can still be changed — the case that fixes a budget
    // imported before any of this existed.
    expect(screen.queryByRole('button', { name: /What arrived/ })).not.toBeInTheDocument()
    expect(screen.getByText('Amazon Prime')).toBeInTheDocument()
  })
})

describe('the tag step', () => {
  async function goToTags(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: /Categories & tags/ }))
  }

  it('opens on the categories the import tagged, and says why', async () => {
    const user = userEvent.setup()
    open()
    await goToTags(user)

    expect(screen.getByText('Amazon Prime')).toBeInTheDocument()
    expect(screen.getByText(/tagged from .Long Term Expenses./)).toBeInTheDocument()
    // Rent was not tagged by the import, so it is not in the opening view.
    expect(screen.queryByText('Rent')).not.toBeInTheDocument()
  })

  it('never offers a category from a system group', async () => {
    const user = userEvent.setup()
    open()
    await goToTags(user)
    await user.click(screen.getByRole('button', { name: /^All/ }))
    // Income holds no envelope money; classifying its spending is meaningless.
    expect(screen.queryByText('Inflow')).not.toBeInTheDocument()
  })

  it('shows a suggestion unchecked and writes nothing on its own', async () => {
    const user = userEvent.setup()
    open()
    await goToTags(user)

    const offer = screen.getByRole('checkbox', { name: /Subscription/ })
    expect(offer).not.toBeChecked()
    await user.click(offer)
    expect(bulkSet).not.toHaveBeenCalled()
  })

  it('sends only what moved, in one request, on Done', async () => {
    const user = userEvent.setup()
    open()
    await goToTags(user)
    await user.click(screen.getByRole('checkbox', { name: /Subscription/ }))
    await user.click(screen.getByRole('button', { name: /Accounts/ }))
    await user.click(screen.getByRole('button', { name: /Save and close/ }))

    await waitFor(() => expect(bulkSet).toHaveBeenCalledTimes(1))
    expect(bulkSet).toHaveBeenCalledWith([
      // The full intended set: the server replaces rather than merges, so the
      // tag it already had has to travel with the one being added.
      { category_id: 'prime', tag_ids: ['t-lte', 't-sub'] },
    ])
    await waitFor(() => expect(markReviewed).toHaveBeenCalled())
  })

  it('marks the review seen even when nothing was changed', async () => {
    const user = userEvent.setup()
    open()
    await user.click(screen.getByRole('button', { name: /Accounts/ }))
    await user.click(screen.getByRole('button', { name: /^Done$/ }))

    await waitFor(() => expect(markReviewed).toHaveBeenCalled())
    expect(bulkSet).not.toHaveBeenCalled()
  })

  it('removes a tag the import got wrong', async () => {
    const user = userEvent.setup()
    open()
    await goToTags(user)
    await user.click(screen.getByRole('button', { name: 'Remove Long-term expense' }))
    await user.click(screen.getByRole('button', { name: /Accounts/ }))
    await user.click(screen.getByRole('button', { name: /Save and close/ }))

    await waitFor(() => expect(bulkSet).toHaveBeenCalledWith([{ category_id: 'prime', tag_ids: [] }]))
  })

  it('reaches the categories the import never touched', async () => {
    const user = userEvent.setup()
    open()
    await goToTags(user)
    await user.click(screen.getByRole('button', { name: /^Suggested/ }))
    expect(screen.getByText('Rent')).toBeInTheDocument()
  })
})
