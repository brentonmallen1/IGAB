/**
 * The assign box reads what a person typed.
 *
 * It called `toCents`, which is `parseFloat` underneath: "1,250" came back as
 * 1. The fault was masked rather than absent — the field was `type="number"`,
 * so the browser refused the comma and handed over an empty string, and the
 * isNaN guard turned that into "Enter an amount greater than zero". Nothing
 * was mis-saved, but the only two money boxes in the app without a
 * calculator also told someone who typed a thousands separator that their
 * amount was not greater than zero.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const moveMoneyMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({})))

vi.mock('../../../api/budgets', () => ({
  useMoveMoney: () => ({ mutateAsync: moveMoneyMutate, isPending: false }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [{ id: 'cat-1', name: 'Groceries', is_assignable: true, category_group_id: 'g1' }],
  }),
  useCategoryGroups: () => ({ data: [{ id: 'g1', name: 'Everyday', is_archived: false }] }),
}))
vi.mock('../../../utils/toastUndo', () => ({ useUndoToast: () => vi.fn() }))

import { AssignManualTab } from './AssignManualTab'

function setup(tba = 5000) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AssignManualTab budgetId="b1" month="2026-09" tba={tba} onDone={vi.fn()} />
    </QueryClientProvider>
  )
  const amount = screen.getByLabelText('Assign') as HTMLInputElement
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'cat-1' } })
  return amount
}

beforeEach(() => moveMoneyMutate.mockClear())

describe('AssignManualTab amount', () => {
  it('reads a typed thousands separator as the number it looks like', async () => {
    const amount = setup(500000)
    fireEvent.change(amount, { target: { value: '1,250' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => expect(moveMoneyMutate).toHaveBeenCalled())
    expect(moveMoneyMutate).toHaveBeenCalledWith(expect.objectContaining({ amount: 1250 }))
  })

  it('is a calculator, like every other money box', async () => {
    // Committed through the same evaluator the field blurs with, so Enter
    // straight out of an unevaluated expression sends the right number.
    const amount = setup()
    fireEvent.change(amount, { target: { value: '40 + 20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    await waitFor(() => expect(moveMoneyMutate).toHaveBeenCalled())
    expect(moveMoneyMutate).toHaveBeenCalledWith(expect.objectContaining({ amount: 60 }))
  })

  it('says what is wrong when the text is not an amount', () => {
    const amount = setup()
    fireEvent.change(amount, { target: { value: 'lunch' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    expect(screen.getByText(/isn’t an amount/)).toBeInTheDocument()
    expect(moveMoneyMutate).not.toHaveBeenCalled()
  })

  it('still refuses zero, in its own words', () => {
    const amount = setup()
    fireEvent.change(amount, { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }))

    expect(screen.getByText('Enter an amount greater than zero')).toBeInTheDocument()
    expect(moveMoneyMutate).not.toHaveBeenCalled()
  })

  it('warns past Ready to Assign using the same reading of the box', () => {
    const amount = setup(100)
    fireEvent.change(amount, { target: { value: '1,250' } })
    expect(screen.getByText(/Exceeds Ready to Assign/)).toBeInTheDocument()
  })
})
