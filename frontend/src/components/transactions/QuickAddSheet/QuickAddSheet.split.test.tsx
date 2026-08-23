/**
 * Splitting a transaction from the phone's quick-add.
 *
 * Before this, the bottom-nav ＋ could only assign one category, and the only
 * way to split on a phone was to save the transaction, find it in the account
 * register, and convert it there. These cover the money-critical half: the
 * legs must sum to the total in integer cents, the parent must not keep a
 * category of its own, and the overspend check must ask about every leg.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TransactionCreate } from '../../../types'

// Typed args, so the assertions below can read what was actually sent.
const createMutate = vi.hoisted(() =>
  vi.fn((_payload: unknown) => Promise.resolve({ id: 'txn-new' }))
)
const confirmOverspend = vi.hoisted(() =>
  vi.fn((_budgetId: string, _affected: unknown, _fmt: unknown) => Promise.resolve(true))
)
const closeQuickAdd = vi.hoisted(() => vi.fn())

vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: createMutate, isPending: false }),
}))
vi.mock('../../../api/budgets', () => ({ confirmFutureOverspend: confirmOverspend }))
vi.mock('../../../api/attachments', () => ({
  ATTACHMENT_ACCEPT: '',
  isAttachableFile: () => true,
  uploadFilesToTransaction: vi.fn(() => Promise.resolve({ failed: [] })),
}))
vi.mock('../../../api/ai', () => ({ useAIStatus: () => ({ data: { enabled: false } }) }))
vi.mock('../../../api/aiJobs', () => ({
  useSubmitReceipt: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/payees', () => ({
  usePayees: () => ({ data: [] }),
  useNearbyPayees: () => ({ data: [] }),
  useCreatePayee: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      { id: 'c1', category_group_id: 'g1', name: 'Groceries', is_hidden: false, linked_account_id: null },
      { id: 'c2', category_group_id: 'g1', name: 'Household', is_hidden: false, linked_account_id: null },
      { id: 'c3', category_group_id: 'g1', name: 'Treats', is_hidden: false, linked_account_id: null },
    ],
  }),
  useCategoryGroups: () => ({ data: [{ id: 'g1', name: 'Everyday' }] }),
}))
vi.mock('../../../api/accounts', () => ({
  useAccounts: () => ({
    data: [{ id: 'acc-1', name: 'Checking', on_budget: true, is_closed: false }],
  }),
}))
vi.mock('../../../stores/appStore', () => ({
  useAppStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      currentBudgetId: 'budget-1',
      lastQuickAddAccountId: null,
      setLastQuickAddAccountId: vi.fn(),
      locationEnabled: false,
    }),
}))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({ quickAddOpen: true, closeQuickAdd }),
}))
vi.mock('../../../hooks/useCurrentPosition', () => ({ useCurrentPosition: () => null }))
vi.mock('../../../hooks/useMediaQuery', () => ({
  useIsTouch: () => true,
  useIsMobile: () => true,
}))
vi.mock('../../ai/NLQuickEntry', () => ({ NLQuickEntry: () => null }))
vi.mock('../../../utils/haptics', () => ({ hapticTick: vi.fn() }))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

import { QuickAddSheet } from './QuickAddSheet'

/** Enter an amount, open the split editor. */
function startSplit(total: string) {
  render(<QuickAddSheet />)
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: total } })
  fireEvent.click(screen.getByTitle('Split this across categories'))
}

/** Pick a category through the shared selection sheet.
 *
 *  The option has to be found inside the sheet specifically: jsdom fires no
 *  transitionend, so a dismissed BottomSheet's rows linger in the DOM and a
 *  bare getByText would match the leg's own label as readily as the option. */
function pickInSheet(name: string) {
  const option = screen
    .getAllByText(name)
    .find((el) => el.className.includes('selection-sheet__option-label'))
  fireEvent.click(option!)
}

function pickLegCategory(legIndex: number, name: string) {
  fireEvent.click(screen.getByLabelText(`Split ${legIndex + 1} category`))
  pickInSheet(name)
}

function setLeg(legIndex: number, amount: string) {
  fireEvent.change(screen.getByLabelText(`Split ${legIndex + 1} amount`), {
    target: { value: amount },
  })
}

const save = () => screen.getByRole('button', { name: 'Save' })
const lastCreate = () => createMutate.mock.calls.at(-1)![0] as unknown as TransactionCreate

beforeEach(() => {
  createMutate.mockClear()
  confirmOverspend.mockClear()
  closeQuickAdd.mockClear()
})

describe('reaching the split editor', () => {
  it('offers a split alongside the category row', () => {
    render(<QuickAddSheet />)
    expect(screen.getByTitle('Split this across categories')).toBeTruthy()
  })

  it('starts with two legs, because a split of one is just a category', () => {
    startSplit('10.00')
    expect(screen.getAllByLabelText(/^Split \d+ amount$/)).toHaveLength(2)
  })

  it('carries an already-chosen category into the first leg', () => {
    render(<QuickAddSheet />)
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '10.00' } })
    fireEvent.click(screen.getByLabelText('Category'))
    pickInSheet('Groceries')
    fireEvent.click(screen.getByTitle('Split this across categories'))
    // The pick survives rather than being thrown away by the mode switch.
    expect(screen.getByLabelText('Split 1 category').textContent).toContain('Groceries')
    expect(screen.getByLabelText('Split 2 category').textContent).toContain('Choose category')
  })

  it('cancelling the split returns to a single category row', () => {
    startSplit('10.00')
    fireEvent.click(screen.getByRole('button', { name: /Cancel split/ }))
    expect(screen.queryByLabelText('Split 1 amount')).toBeNull()
    expect(screen.getByTitle('Split this across categories')).toBeTruthy()
  })

  it('will not drop below two legs', () => {
    startSplit('10.00')
    expect(screen.getByLabelText('Remove split 1').hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /Add split/ }))
    expect(screen.getByLabelText('Remove split 1').hasAttribute('disabled')).toBe(false)
    fireEvent.click(screen.getByLabelText('Remove split 3'))
    expect(screen.getAllByLabelText(/^Split \d+ amount$/)).toHaveLength(2)
  })
})

describe('the legs must add up', () => {
  it('blocks the save until they do', () => {
    startSplit('10.00')
    pickLegCategory(0, 'Groceries')
    pickLegCategory(1, 'Household')
    setLeg(0, '6.00')
    expect(save().hasAttribute('disabled')).toBe(true)
    setLeg(1, '4.00')
    expect(save().hasAttribute('disabled')).toBe(false)
  })

  it('reports what is left, and says so when nothing is', () => {
    startSplit('10.00')
    setLeg(0, '6.00')
    expect(screen.getByRole('status').textContent).toContain('left')
    setLeg(1, '4.00')
    expect(screen.getByRole('status').textContent).toBe('Fully assigned')
  })

  it('says "over" rather than a negative remainder', () => {
    startSplit('10.00')
    setLeg(0, '12.00')
    expect(screen.getByRole('status').textContent).toContain('over')
  })

  it('accepts legs that only sum exactly in integer cents', () => {
    // 0.10 + 0.20 !== 0.30 in float; the comparison must be in cents.
    startSplit('0.30')
    pickLegCategory(0, 'Groceries')
    pickLegCategory(1, 'Household')
    setLeg(0, '0.10')
    setLeg(1, '0.20')
    expect(screen.getByRole('status').textContent).toBe('Fully assigned')
    expect(save().hasAttribute('disabled')).toBe(false)
  })

  it('blocks a leg with no category even when the amounts balance', () => {
    startSplit('10.00')
    pickLegCategory(0, 'Groceries')
    setLeg(0, '6.00')
    setLeg(1, '4.00')
    expect(screen.getByRole('status').textContent).toBe('Fully assigned')
    expect(save().hasAttribute('disabled')).toBe(true)
  })

  it('blocks a zero-amount leg', () => {
    startSplit('10.00')
    pickLegCategory(0, 'Groceries')
    pickLegCategory(1, 'Household')
    setLeg(0, '10.00')
    setLeg(1, '0')
    expect(save().hasAttribute('disabled')).toBe(true)
  })
})

describe('what gets sent', () => {
  async function saveSplit(total: string, legs: [string, string][]) {
    startSplit(total)
    // Two legs come for free; anything beyond that has to be added.
    for (let i = 2; i < legs.length; i++) {
      fireEvent.click(screen.getByRole('button', { name: /Add split/ }))
    }
    legs.forEach(([name, amount], i) => {
      pickLegCategory(i, name)
      setLeg(i, amount)
    })
    fireEvent.click(save())
    await waitFor(() => expect(createMutate).toHaveBeenCalled())
  }

  it('sends the legs and leaves the parent uncategorised', async () => {
    await saveSplit('10.00', [
      ['Groceries', '6.00'],
      ['Household', '4.00'],
    ])
    const payload = lastCreate()
    expect(payload.category_id).toBeUndefined()
    expect(payload.amount).toBe(-10)
    expect(payload.splits).toEqual([
      { amount: -6, category_id: 'c1', memo: undefined },
      { amount: -4, category_id: 'c2', memo: undefined },
    ])
  })

  it('signs the legs with the direction, so an inflow split is positive', async () => {
    startSplit('10.00')
    fireEvent.click(screen.getByRole('radio', { name: 'Received' }))
    pickLegCategory(0, 'Groceries')
    pickLegCategory(1, 'Household')
    setLeg(0, '6.00')
    setLeg(1, '4.00')
    fireEvent.click(save())
    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    const payload = lastCreate()
    expect(payload.amount).toBe(10)
    expect(payload.splits?.map((s) => s.amount)).toEqual([6, 4])
  })

  it('asks about overspend for every leg, not the parent', async () => {
    await saveSplit('10.00', [
      ['Groceries', '6.00'],
      ['Household', '4.00'],
    ])
    const affected = confirmOverspend.mock.calls.at(-1)![1] as {
      category_id: string
      amount_delta: number
    }[]
    expect(affected.map((a) => a.category_id)).toEqual(['c1', 'c2'])
    expect(affected.map((a) => a.amount_delta)).toEqual([-6, -4])
  })

  it('does not save when the overspend warning is declined', async () => {
    confirmOverspend.mockResolvedValueOnce(false)
    startSplit('10.00')
    pickLegCategory(0, 'Groceries')
    pickLegCategory(1, 'Household')
    setLeg(0, '6.00')
    setLeg(1, '4.00')
    fireEvent.click(save())
    await waitFor(() => expect(confirmOverspend).toHaveBeenCalled())
    expect(createMutate).not.toHaveBeenCalled()
  })

  it('sends no splits at all when the split was cancelled', async () => {
    startSplit('10.00')
    fireEvent.click(screen.getByRole('button', { name: /Cancel split/ }))
    fireEvent.click(screen.getByLabelText('Category'))
    pickInSheet('Groceries')
    fireEvent.click(save())
    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    const payload = lastCreate()
    expect(payload.splits).toBeUndefined()
    expect(payload.category_id).toBe('c1')
  })
})
