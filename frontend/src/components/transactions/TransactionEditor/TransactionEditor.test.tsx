/**
 * Money-critical tests for the transaction editor: outflow/inflow signing,
 * the future-overspend confirm gate (B1), edit reversals, and split-mode
 * integer-cents validation gating the submit button.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const createMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({ id: 'new-txn' })))
// Typed payload: the transfer tests assert on the ORDER and content of two
// separate PATCHes (break, then edit), so the calls must stay inspectable.
const updateMutate = vi.hoisted(() =>
  vi.fn((_payload: Record<string, unknown>) => Promise.resolve({}))
)
const deleteMutate = vi.hoisted(() => vi.fn(() => Promise.resolve()))
const convertMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({})))
const confirmOverspend = vi.hoisted(() => vi.fn(() => Promise.resolve(true)))
const toastError = vi.hoisted(() => vi.fn())

vi.mock('react-hot-toast', () => ({ default: { error: toastError, success: vi.fn() } }))

const GROUPS = vi.hoisted(() => [{ id: 'g1', name: 'Everyday', is_archived: false }])
const CATEGORIES = vi.hoisted(() => [
  {
    id: 'cat-1',
    category_group_id: 'g1',
    name: 'Groceries',
    is_archived: false,
    linked_account_id: null,
    linked_liability_id: null,
    is_assignable: true,
    is_fundable: true,
    is_categorizable: true,
  },
  {
    id: 'cat-2',
    category_group_id: 'g1',
    name: 'Fun',
    is_archived: false,
    linked_account_id: null,
    linked_liability_id: null,
    is_assignable: true,
    is_fundable: true,
    is_categorizable: true,
  },
])
const ACCOUNTS = vi.hoisted(() => [
  { id: 'acc-1', name: 'Checking', on_budget: true, is_closed: false },
  { id: 'acc-2', name: 'Savings', on_budget: true, is_closed: false },
  { id: 'acc-3', name: 'Vacation Fund', on_budget: true, is_closed: false },
])

let classificationData: unknown = undefined
/** Rows in the target account that could be a transfer's far leg. */
let transferCandidates: unknown[] = []

vi.mock('../../../api/transactions', () => ({
  useCreateTransaction: () => ({ mutateAsync: createMutate, isPending: false }),
  useUpdateTransaction: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteTransaction: () => ({ mutateAsync: deleteMutate, isPending: false }),
  useConvertToSplit: () => ({ mutateAsync: convertMutate, isPending: false }),
  useReplaceSplits: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTransactionSplits: () => ({ data: undefined }),
  useTransaction: () => ({ data: undefined }),
  usePayees: () => ({ data: [] }),
  useSimilarTransactions: () => ({ data: [] }),
  useTransactionClassification: () => ({ data: classificationData }),
  useTransferCandidates: () => ({ data: transferCandidates }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: CATEGORIES }),
  useCategoryGroups: () => ({ data: GROUPS }),
  useRecentPayeeForCategory: () => ({ data: undefined }),
}))
vi.mock('../../../api/accounts', () => ({ useAccounts: () => ({ data: ACCOUNTS }) }))
vi.mock('../../../api/ai', () => ({
  useAIStatus: () => ({ data: { available: false } }),
  useSuggestCategory: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/aiJobs', () => ({
  useSubmitReceipt: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReprocessAIJob: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('../../../api/attachments', () => ({
  ATTACHMENT_ACCEPT: 'image/*,application/pdf',
  isAttachableFile: () => true,
}))
vi.mock('../../../api/budgets', () => ({ confirmFutureOverspend: confirmOverspend }))
vi.mock('../../attachments/AttachmentPanel', () => ({ AttachmentPanel: () => null }))
vi.mock('../../ai/ReceiptPane', () => ({ ReceiptPane: () => null }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../../../hooks/useHistoryDismissable', () => ({ useHistoryDismissable: () => {} }))

import { TransactionEditor } from './TransactionEditor'
import type { Transaction } from '../../../types'

function renderEditor(props: Partial<Parameters<typeof TransactionEditor>[0]> = {}) {
  // The api/* hooks are mocked, but useToastUndo reaches the real
  // useQueryClient — without a provider every render in this file throws
  // before a single assertion runs.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <TransactionEditor
        budgetId="b1"
        accountId="acc-1"
        transaction={null}
        onClose={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

function amountInputs() {
  // Non-split mode renders exactly two 0.00 inputs: [outflow, inflow]
  return screen.getAllByPlaceholderText('0.00')
}

function submitButton(name = 'Add') {
  return screen.getByRole('button', { name })
}

/**
 * Category is picked through CategoryCombobox, not a native <select>: focus
 * opens the portalled listbox, typing filters it, and options commit on
 * mousedown (so the input never blurs first).
 */
function pickCategory(name: string, label = 'Category', index = 0) {
  const input = screen.getAllByRole('combobox', { name: label })[index]
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: name } })
  const option = screen.getAllByRole('option', { name }).at(-1)!
  fireEvent.mouseDown(option)
}

function setDate(value: string) {
  const dateInput = document.querySelector('input[type="date"]')!
  fireEvent.change(dateInput, { target: { value } })
}

describe('TransactionEditor amount signing', () => {
  beforeEach(() => {
    createMutate.mockClear()
    updateMutate.mockClear()
    convertMutate.mockClear()
    confirmOverspend.mockClear()
    confirmOverspend.mockImplementation(() => Promise.resolve(true))
  })

  it('saves an outflow as a negative amount', async () => {
    renderEditor()
    fireEvent.change(amountInputs()[0], { target: { value: '12.34' } })
    fireEvent.click(submitButton())

    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({ account_id: 'acc-1', amount: -12.34, approved: true })
    )
  })

  it('saves an inflow as a positive amount', async () => {
    renderEditor()
    fireEvent.change(amountInputs()[1], { target: { value: '250' } })
    fireEvent.click(submitButton())

    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    expect(createMutate).toHaveBeenCalledWith(expect.objectContaining({ amount: 250 }))
  })

  it('typing an outflow clears the inflow — an amount can never be both', () => {
    renderEditor()
    const [outflow, inflow] = amountInputs()
    fireEvent.change(inflow, { target: { value: '5' } })
    fireEvent.change(outflow, { target: { value: '10' } })
    expect((inflow as HTMLInputElement).value).toBe('')
  })
})

describe('TransactionEditor future-overspend gate (B1)', () => {
  beforeEach(() => {
    createMutate.mockClear()
    updateMutate.mockClear()
    confirmOverspend.mockClear()
    confirmOverspend.mockImplementation(() => Promise.resolve(true))
  })

  it('sends the categorized amount as a probe before saving', async () => {
    renderEditor()
    setDate('2030-01-15')
    pickCategory('Groceries')
    fireEvent.change(amountInputs()[0], { target: { value: '50' } })
    fireEvent.click(submitButton())

    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    expect(confirmOverspend).toHaveBeenCalledWith(
      'b1',
      [{ category_id: 'cat-1', date: '2030-01-15', amount_delta: -50 }],
      expect.any(Function)
    )
  })

  it('does not save when the user declines the warning', async () => {
    confirmOverspend.mockImplementation(() => Promise.resolve(false))
    renderEditor()
    pickCategory('Groceries')
    fireEvent.change(amountInputs()[0], { target: { value: '50' } })
    fireEvent.click(submitButton())

    await waitFor(() => expect(confirmOverspend).toHaveBeenCalled())
    expect(createMutate).not.toHaveBeenCalled()
  })

  it('includes a reversal probe when editing, so only the net change counts', async () => {
    const txn = {
      id: 't1',
      account_id: 'acc-1',
      date: '2030-01-10',
      amount: -20,
      category_id: 'cat-1',
      payee_id: null,
      memo: null,
      cleared: 'uncleared',
      transfer_id: null,
    } as unknown as Transaction
    renderEditor({ transaction: txn, accountId: null })

    fireEvent.change(amountInputs()[0], { target: { value: '50' } })
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    expect(confirmOverspend).toHaveBeenCalledWith(
      'b1',
      [
        { category_id: 'cat-1', date: '2030-01-10', amount_delta: -50 },
        { category_id: 'cat-1', date: '2030-01-10', amount_delta: 20 },
      ],
      expect.any(Function)
    )
  })
})

describe('TransactionEditor split-mode validation', () => {
  beforeEach(() => {
    createMutate.mockClear()
    confirmOverspend.mockClear()
    confirmOverspend.mockImplementation(() => Promise.resolve(true))
  })

  function enterSplitMode() {
    fireEvent.click(screen.getByTitle('Split this transaction'))
  }

  it('disables submit until splits sum to the total in integer cents with categories', async () => {
    renderEditor()
    fireEvent.change(amountInputs()[0], { target: { value: '1.10' } })
    enterSplitMode()

    expect(submitButton()).toBeDisabled()

    const splitAmounts = screen
      .getAllByPlaceholderText('0.00')
      .filter((el) => el.classList.contains('txn-editor__split-amount'))

    fireEvent.change(splitAmounts[0], { target: { value: '1.00' } })
    fireEvent.change(splitAmounts[1], { target: { value: '0.10' } })
    expect(screen.getByText('Fully assigned')).toBeInTheDocument()
    // Amounts right but categories missing — still blocked
    expect(submitButton()).toBeDisabled()

    // Two split rows, one category picker each
    pickCategory('Groceries', 'Split category', 0)
    pickCategory('Fun', 'Split category', 1)
    expect(submitButton()).toBeEnabled()

    fireEvent.click(submitButton())
    await waitFor(() => expect(createMutate).toHaveBeenCalled())
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        amount: -1.1,
        splits: [
          expect.objectContaining({ amount: -1, category_id: 'cat-1' }),
          expect.objectContaining({ amount: -0.1, category_id: 'cat-2' }),
        ],
      })
    )
  })
})

describe('TransactionEditor classification note', () => {
  const savedTxn = {
    id: 't-1',
    account_id: 'acc-1',
    date: '2030-01-10',
    amount: -500,
    category_id: 'cat-1',
    payee_id: null,
    memo: null,
    cleared: 'uncleared',
    transfer_id: null,
  } as unknown as Transaction

  beforeEach(() => {
    classificationData = undefined
  })

  it('explains why a row counts the way it does', () => {
    classificationData = {
      activity_class: 'savings',
      label: 'Savings',
      reason: 'transfer_to_tracked_asset',
      explanation: 'it moves money to a tracked account you own',
    }
    renderEditor({ transaction: savedTxn, accountId: null })

    expect(screen.getByText(/Counts as/)).toBeInTheDocument()
    expect(screen.getByText('Savings')).toBeInTheDocument()
    expect(screen.getByText(/moves money to a tracked account you own/)).toBeInTheDocument()
  })

  it('says nothing for an unsaved draft', () => {
    renderEditor({ transaction: null })
    expect(screen.queryByText(/Counts as/)).not.toBeInTheDocument()
  })
})

/**
 * Repairing a transfer by hand. This control existed but did nothing: the
 * server dropped the field, and the editor never showed an existing
 * transfer's destination — so the one manual fix for an unpaired leg was
 * unreachable.
 */
describe('TransactionEditor transfers', () => {
  const linkedLeg = {
    id: 't-xfer',
    account_id: 'acc-1',
    date: '2026-08-20',
    amount: -500,
    category_id: null,
    payee_id: 'p-transfer',
    memo: null,
    cleared: 'uncleared',
    transfer_id: 't-far',
    counterpart_account_id: 'acc-2',
  } as unknown as Transaction

  /** The importer's leftovers: transfer-shaped, but never linked. */
  const orphanLeg = {
    ...linkedLeg,
    id: 't-orphan',
    transfer_id: null,
  } as unknown as Transaction

  beforeEach(() => {
    updateMutate.mockClear()
    transferCandidates = []
  })

  it('opens an existing transfer showing where it goes', () => {
    renderEditor({ transaction: linkedLeg })
    const select = screen.getByRole('combobox', { name: 'To Account' })
    expect((select as HTMLSelectElement).value).toBe('acc-2')
  })

  it('treats an unpaired leg as a transfer too', () => {
    // transfer_id is null here — reading only that is what made the repair
    // path invisible on exactly the rows that needed it.
    renderEditor({ transaction: orphanLeg })
    expect(screen.getByRole('combobox', { name: 'To Account' })).toBeInTheDocument()
  })

  it('sends the new destination when retargeted', async () => {
    renderEditor({ transaction: linkedLeg })
    fireEvent.change(screen.getByRole('combobox', { name: 'To Account' }), {
      target: { value: 'acc-3' },
    })
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 't-xfer', transfer_account_id: 'acc-3' })
    )
  })

  it('breaks the link as its own step when the toggle goes off', async () => {
    renderEditor({ transaction: linkedLeg })
    fireEvent.click(screen.getByLabelText('Transfer to account'))
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(2))
    // A linked leg's payee IS its destination, so the server refuses a payee
    // and a link instruction in one request — break first, then edit.
    expect(updateMutate.mock.calls[0][0]).toEqual({
      id: 't-xfer',
      transfer_account_id: null,
    })
    expect(updateMutate.mock.calls[1][0]).not.toHaveProperty('transfer_account_id')
  })

  it('asks which row is the far leg when more than one could be', async () => {
    transferCandidates = [
      {
        id: 'cand-1',
        date: '2026-08-20',
        amount: 500.0,
        memo: 'ACH credit',
        cleared: 'cleared',
      },
      { id: 'cand-2', date: '2026-08-20', amount: '500.00', memo: 'Deposit', cleared: 'uncleared' },
    ]
    renderEditor({ transaction: orphanLeg })

    expect(screen.getByText(/which transaction in savings/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /ACH credit/ }))
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ transfer_partner_transaction_id: 'cand-1' })
    )
  })

  it('holds Save until the partner question is answered', () => {
    // Found in review: submitting with the question unanswered sent a request
    // the server can only refuse — and the refusal was swallowed, so Save
    // just re-enabled with nothing saved and nothing said.
    transferCandidates = [
      {
        id: 'cand-1',
        date: '2026-08-20',
        amount: 500.0,
        memo: 'ACH credit',
        cleared: 'cleared',
      },
      { id: 'cand-2', date: '2026-08-20', amount: '500.00', memo: 'Deposit', cleared: 'uncleared' },
    ]
    renderEditor({ transaction: orphanLeg })

    expect(submitButton('Save')).toBeDisabled()
    fireEvent.click(screen.getByRole('radio', { name: /ACH credit/ }))
    expect(submitButton('Save')).toBeEnabled()
  })

  it('says so when the server refuses the save, and stays open', async () => {
    const onClose = vi.fn()
    updateMutate.mockRejectedValueOnce(new Error('refused'))
    renderEditor({ transaction: linkedLeg, onClose })
    fireEvent.change(screen.getByRole('combobox', { name: 'To Account' }), {
      target: { value: 'acc-3' },
    })
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(toastError).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
  })

  it('can say none of these, write the missing one', async () => {
    transferCandidates = [
      { id: 'cand-1', date: '2026-08-20', amount: '500.00', memo: 'Unrelated', cleared: 'cleared' },
    ]
    renderEditor({ transaction: orphanLeg })

    fireEvent.click(screen.getByRole('radio', { name: /None of these/ }))
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ transfer_create_partner: true })
    )
  })

  it('asks nothing when there is no candidate to confuse it with', () => {
    renderEditor({ transaction: orphanLeg })
    expect(screen.queryByText(/which transaction in/i)).not.toBeInTheDocument()
  })
})

describe('TransactionEditor on a reconciled transaction', () => {
  // Reconciliation locks the money (backend domain/reconciliation.py): the
  // amount, date and cleared state are shown locked and never sent; the
  // bookkeeping — memo, category, payee — still saves.
  const reconciled = {
    id: 't9',
    account_id: 'acc-1',
    date: '2030-01-10',
    amount: -20,
    category_id: 'cat-1',
    payee_id: null,
    memo: 'old note',
    cleared: 'reconciled',
    transfer_id: null,
    is_split: false,
  } as unknown as Transaction

  beforeEach(() => {
    updateMutate.mockClear()
    confirmOverspend.mockClear()
    confirmOverspend.mockImplementation(() => Promise.resolve(true))
  })

  it('locks the money and leaves the bookkeeping editable', async () => {
    renderEditor({ transaction: reconciled, accountId: null })

    expect(document.querySelector('input[type="date"]')).toBeDisabled()
    amountInputs().forEach((input) => expect(input).toBeDisabled())
    expect(screen.getByLabelText('Cleared: reconciled')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('locked')

    fireEvent.change(screen.getByPlaceholderText('Optional note...'), {
      target: { value: 'filed properly' },
    })
    fireEvent.click(submitButton('Save'))

    await waitFor(() => expect(updateMutate).toHaveBeenCalled())
    const sent = updateMutate.mock.calls[0][0]
    expect(sent).toMatchObject({ id: 't9', memo: 'filed properly' })
    expect(sent).not.toHaveProperty('amount')
    expect(sent).not.toHaveProperty('date')
    expect(sent).not.toHaveProperty('cleared')
  })
})
