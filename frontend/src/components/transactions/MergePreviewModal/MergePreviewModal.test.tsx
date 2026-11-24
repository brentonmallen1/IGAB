/**
 * The merge dialog shows what merging leaves behind, and asks only about
 * what is a choice.
 *
 * It used to show the two rows and a "Keep" badge and nothing of the result:
 * with a split on one side the category read as simply dropped, under a note
 * about lines having to "add up". The result is the server's now
 * (`useMergePreview`, mocked here as the wire answer); this suite pins what
 * the dialog does with it. That the preview IS the merge is the backend's to
 * prove — tests/integration/test_merge_preview.py.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { MergeKeep, MergePreview, Transaction } from '../../../types'
import { makeTransaction } from '../../../test-utils/factories'

const api = vi.hoisted(() => ({
  /** What the server answers for a given `keep`. */
  preview: (_keep: unknown): unknown => undefined,
  error: null as unknown,
  asked: [] as unknown[],
  lines: {} as Record<string, unknown[]>,
}))
vi.mock('../../../api/transactions', () => ({
  useMergePreview: (_budget: string, ids: unknown, keep: unknown) => {
    api.asked.push({ ids, keep })
    return api.error
      ? { data: undefined, isError: true, error: api.error }
      : { data: api.preview(keep), isError: false, error: null }
  },
  useTransactionSplits: (id: string, enabled: boolean) => ({
    data: enabled ? api.lines[id] : undefined,
  }),
}))

import { MergePreviewModal } from './MergePreviewModal'

const ENTERED = makeTransaction({
  id: 'entered',
  date: '2026-11-03',
  amount: -80,
  payee_id: 'p-grocer',
  category_id: 'c-groceries',
  memo: 'weekly shop',
  cleared: 'uncleared',
})
const BANK = makeTransaction({
  id: 'bank',
  date: '2026-11-04',
  amount: -80,
  payee_id: 'p-bank',
  category_id: 'c-household',
  memo: 'card purchase',
  cleared: 'cleared',
  has_sync_source: true,
})

const payees = new Map([
  ['p-grocer', 'Corner Grocer'],
  ['p-bank', 'CORNER GROCER 114'],
])
const labels = new Map([
  ['c-groceries', { name: 'Groceries', group: 'Everyday' }],
  ['c-household', { name: 'Household', group: 'Everyday' }],
])

/** The server's default for this pair, with `keep` applied the way
 *  `merge_bookkeeping` does — enough of it to drive the dialog. */
function answer(keep: MergeKeep = {}, over: Partial<MergePreview> = {}): MergePreview {
  const from = (field: keyof MergeKeep) => keep[field] ?? 'entered'
  const row = (id: string) => (id === 'bank' ? BANK : ENTERED)
  const memo = keep.memo ?? 'both'
  return {
    survivor_id: 'entered',
    deleted_id: 'bank',
    date: row(from('date')).date,
    amount: -80,
    replaced_amount: null,
    payee_id: row(from('payee')).payee_id,
    payee_name: payees.get(row(from('payee')).payee_id ?? '') ?? null,
    category_id: row(from('category')).category_id,
    memo: memo === 'both' ? 'weekly shop — card purchase' : row(memo).memo,
    cleared: 'cleared',
    is_split: false,
    lines: [],
    has_bank_record: true,
    import_description: null,
    bank_posted_date: '2026-11-04',
    transfer: null,
    choices: {
      date: { source: from('date'), choosable: true },
      payee: { source: from('payee'), choosable: true },
      category: { source: from('category'), choosable: true },
      memo: { source: memo, choosable: true },
    },
    ...over,
  }
}

function open(props: { transactions?: [Transaction, Transaction]; error?: string } = {}) {
  const onConfirm = vi.fn()
  render(
    <MergePreviewModal
      budgetId="b1"
      transactions={props.transactions ?? [ENTERED, BANK]}
      payeeMap={payees}
      categoryLabels={labels}
      accountOnBudget
      onConfirm={onConfirm}
      onCancel={vi.fn()}
      isPending={false}
      error={props.error}
    />
  )
  return { onConfirm }
}

const card = (name: string) => screen.getByRole('region', { name })
const result = () => screen.getByRole('region', { name: 'After merging' })

beforeEach(async () => {
  // Dialog pushes a history entry; let the last test's unwind first.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  api.preview = (keep) => answer(keep as MergeKeep)
  api.error = null
  api.asked = []
  api.lines = {}
})

describe('what merging leaves behind', () => {
  it('shows the merged transaction, not just which row is kept', () => {
    open()
    const after = within(result())
    expect(after.getByText('Corner Grocer')).toBeInTheDocument()
    expect(after.getByText('Groceries')).toBeInTheDocument()
    expect(after.getByText('weekly shop — card purchase')).toBeInTheDocument()
    // The bank's copy contributes its record and clears the row.
    expect(after.getByText('cleared')).toBeInTheDocument()
    expect(after.getByText('Bank record')).toBeInTheDocument()
  })

  it('names the two cards for where the rows came from', () => {
    open()
    expect(card('Entered by hand')).toBeInTheDocument()
    expect(card('From the bank')).toBeInTheDocument()
  })

  it('lists a split’s lines in the result — they were what looked dropped', () => {
    const split = { ...ENTERED, is_split: true, category_id: null }
    api.lines = {
      entered: [
        { amount: -62, category_id: 'c-groceries' },
        { amount: -18, category_id: 'c-household' },
      ],
    }
    api.preview = () =>
      answer(
        {},
        {
          is_split: true,
          category_id: null,
          lines: [
            { amount: -62, category_id: 'c-groceries', memo: null },
            { amount: -18, category_id: 'c-household', memo: null },
          ],
          choices: {
            ...answer().choices,
            category: { source: 'entered', choosable: false },
            date: { source: 'entered', choosable: false },
          },
        }
      )
    open({ transactions: [split, BANK] })

    const after = within(result())
    expect(after.getByText('Split, 2 lines')).toBeInTheDocument()
    expect(after.getByText('Groceries')).toBeInTheDocument()
    expect(after.getByText('$62.00')).toBeInTheDocument()
    expect(after.getByText('Household')).toBeInTheDocument()
    expect(after.getByText('$18.00')).toBeInTheDocument()
    // The split's own card lists them too, so the two can be read together.
    expect(within(card('Entered by hand')).getByText('$62.00')).toBeInTheDocument()
    // Its category is its lines': not something to pick against "Household".
    expect(
      within(card('From the bank')).queryByRole('radio', { name: 'Keep this category' })
    ).toBeNull()
  })

  it('says when the bank’s amount replaces the one entered', () => {
    api.preview = () => answer({}, { amount: -83.5, replaced_amount: -80 })
    open()
    expect(
      screen.getByText(/The bank posted \$83\.50, so it replaces the \$80\.00 that was entered/)
    ).toBeInTheDocument()
  })

  it('says what becomes of a transfer', () => {
    api.preview = () => answer({}, { transfer: 'taken_over' })
    open()
    expect(screen.getByText(/takes over the transfer/)).toBeInTheDocument()
  })
})

describe('choosing what to keep', () => {
  it('offers a pick only where the server says the rows disagree', () => {
    api.preview = () =>
      answer(
        {},
        {
          choices: {
            ...answer().choices,
            date: { source: 'entered', choosable: false },
            memo: { source: 'entered', choosable: false },
          },
        }
      )
    open()
    expect(screen.getAllByRole('radio', { name: 'Keep this payee' })).toHaveLength(2)
    expect(screen.getAllByRole('radio', { name: 'Keep this category' })).toHaveLength(2)
    expect(screen.queryByRole('radio', { name: 'Keep this date' })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: 'Keep this memo' })).toBeNull()
  })

  it('starts on the server’s defaults: the entered row’s values, both memos', () => {
    open()
    const entered = within(card('Entered by hand'))
    const bank = within(card('From the bank'))
    expect(entered.getByRole('radio', { name: 'Keep this payee' })).toBeChecked()
    expect(bank.getByRole('radio', { name: 'Keep this payee' })).not.toBeChecked()
    expect(entered.getByRole('checkbox', { name: 'Keep this memo' })).toBeChecked()
    expect(bank.getByRole('checkbox', { name: 'Keep this memo' })).toBeChecked()
  })

  it('asks the server again with the pick, and shows its answer', () => {
    open()
    fireEvent.click(within(card('From the bank')).getByRole('radio', { name: 'Keep this payee' }))

    expect(api.asked.at(-1)).toEqual({ ids: ['entered', 'bank'], keep: { payee: 'bank' } })
    expect(within(result()).getByText('CORNER GROCER 114')).toBeInTheDocument()
    expect(
      within(card('From the bank')).getByRole('radio', { name: 'Keep this payee' })
    ).toBeChecked()
  })

  it('takes one memo out, and will not take out the last', () => {
    open()
    const bankMemo = () =>
      within(card('From the bank')).getByRole('checkbox', { name: 'Keep this memo' })
    const enteredMemo = () =>
      within(card('Entered by hand')).getByRole('checkbox', { name: 'Keep this memo' })

    fireEvent.click(bankMemo())
    expect(within(result()).getByText('weekly shop')).toBeInTheDocument()
    expect(bankMemo()).not.toBeChecked()

    fireEvent.click(enteredMemo())
    expect(enteredMemo()).toBeChecked()
  })

  it('"Use all" takes every choice from one card', () => {
    open()
    fireEvent.click(within(card('From the bank')).getByRole('button', { name: 'Use all' }))
    expect(api.asked.at(-1)).toMatchObject({
      keep: { date: 'bank', payee: 'bank', category: 'bank', memo: 'bank' },
    })
    expect(within(card('From the bank')).getByRole('button', { name: 'Use all' })).toBeDisabled()
  })

  it('has nothing to pick, and says nothing about picking, when the rows agree', () => {
    api.preview = () =>
      answer(
        {},
        {
          choices: {
            date: { source: 'entered', choosable: false },
            payee: { source: 'entered', choosable: false },
            category: { source: 'entered', choosable: false },
            memo: { source: null, choosable: false },
          },
        }
      )
    open()
    expect(screen.queryByText(/disagree in places/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Use all' })).toBeNull()
  })
})

describe('merging', () => {
  it('sends the picks the result was showing', () => {
    const { onConfirm } = open()
    fireEvent.click(
      within(card('From the bank')).getByRole('radio', { name: 'Keep this category' })
    )
    fireEvent.click(screen.getByRole('button', { name: 'Merge' }))
    expect(onConfirm).toHaveBeenCalledWith({ category: 'bank' })
  })

  it('sends no picks when none were made — the server’s defaults stand', () => {
    const { onConfirm } = open()
    fireEvent.click(screen.getByRole('button', { name: 'Merge' }))
    expect(onConfirm).toHaveBeenCalledWith({})
  })

  it('says why before the click when the server would refuse, and offers no Merge', () => {
    api.error = {
      isAxiosError: true,
      response: {
        status: 400,
        data: { detail: 'Both transactions are linked to different bank transactions' },
      },
    }
    open()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'These can’t be merged: Both transactions are linked to different bank transactions'
    )
    expect(screen.getByRole('button', { name: 'Merge' })).toBeDisabled()
    expect(screen.queryByRole('region', { name: 'After merging' })).toBeNull()
  })

  it('cannot merge before the server has said what the result is', () => {
    api.preview = () => undefined
    open()
    expect(screen.getByRole('status')).toHaveTextContent('Working out the result')
    expect(screen.getByRole('button', { name: 'Merge' })).toBeDisabled()
  })

  it('shows a refusal of the merge itself instead of leaving the button silent', () => {
    // The rows can change under an open dialog; this used to be swallowed.
    open({ error: 'Both transactions are linked to different bank transactions' })
    expect(
      screen.getByText('Both transactions are linked to different bank transactions')
    ).toBeInTheDocument()
  })
})

describe('the result, for a row taking a transfer over', () => {
  // The link is written after the merge and decides both. The payee is the
  // server's name for it — it may not exist yet, so there is no id to look
  // up — and the category reads as a transfer's, by the register's rule.
  it('reads the transfer payee the server names, and "Transfer" for the category', () => {
    api.preview = () =>
      answer(
        {},
        {
          transfer: 'taken_over',
          payee_id: null,
          payee_name: 'Transfer : Sapphire Visa',
          category_id: null,
        }
      )
    open()
    expect(within(result()).getByText('Transfer : Sapphire Visa')).toBeInTheDocument()
    expect(within(result()).getByText('Transfer')).toBeInTheDocument()
  })

  it('says the merged row still needs a category when the kept row does', () => {
    api.preview = () => answer({}, { category_id: null })
    open({
      transactions: [
        { ...ENTERED, category_id: null, needs_category: true },
        { ...BANK, category_id: null, needs_category: false },
      ],
    })
    expect(within(result()).getByText('Needs Category')).toBeInTheDocument()
  })
})

describe('the category line on a card', () => {
  // The register row's own label: a card used to read a row needing a
  // category as "—", the same as a transfer.
  it('says a row needs a category, not "—"', () => {
    open({
      transactions: [
        { ...ENTERED, category_id: null, needs_category: true },
        { ...BANK, category_id: null, needs_category: false },
      ],
    })
    expect(within(card('Entered by hand')).getByText('Needs Category')).toBeInTheDocument()
    expect(within(card('From the bank')).getByText('Transfer')).toBeInTheDocument()
  })
})
