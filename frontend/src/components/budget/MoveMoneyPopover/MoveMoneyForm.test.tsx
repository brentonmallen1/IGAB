/**
 * Covering an overspent envelope reads what a person typed.
 *
 * Same fault as the assign box, and the same mask: `toCents` is `parseFloat`
 * underneath, but `type="number"` refused the comma before it got there, so
 * someone who typed "1,250" was told to enter an amount greater than zero.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const moveMoneyMutate = vi.hoisted(() => vi.fn(() => Promise.resolve({})))

vi.mock('../../../api/budgets', () => ({
  useMoveMoney: () => ({ mutateAsync: moveMoneyMutate, isPending: false }),
  useMoveHistory: () => ({ data: [] }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      { id: 'cat-1', name: 'Groceries', is_assignable: true, category_group_id: 'g1' },
      { id: 'cat-2', name: 'Fun', is_assignable: true, category_group_id: 'g1' },
    ],
  }),
  useCategoryGroups: () => ({ data: [{ id: 'g1', name: 'Everyday', is_archived: false }] }),
}))
vi.mock('../../common/CategoryCombobox/CategoryCombobox', () => ({
  CategoryCombobox: () => null,
}))

import { MoveMoneyForm } from './MoveMoneyForm'
import type { Category } from '../../../types'

const CATEGORY = { id: 'cat-1', name: 'Groceries' } as unknown as Category

/** Overspent, so the form opens as "Cover Overspending". */
function setup(available = -41.8) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MoveMoneyForm
        budgetId="b1"
        month="2026-09"
        category={CATEGORY}
        available={available}
        onClose={vi.fn()}
      />
    </QueryClientProvider>
  )
  return screen.getByLabelText('Amount') as HTMLInputElement
}

const submit = () => screen.getByRole('button', { name: /Cover Overspending|Move Money/ })

beforeEach(() => moveMoneyMutate.mockClear())

describe('MoveMoneyForm amount', () => {
  it('reads a typed thousands separator as the number it looks like', async () => {
    const amount = setup(-1250)
    fireEvent.change(amount, { target: { value: '1,250' } })
    fireEvent.click(submit())

    await waitFor(() => expect(moveMoneyMutate).toHaveBeenCalled())
    expect(moveMoneyMutate).toHaveBeenCalledWith(expect.objectContaining({ amount: 1250 }))
  })

  it('is a calculator, like every other money box', async () => {
    const amount = setup()
    fireEvent.change(amount, { target: { value: '40 + 20' } })
    fireEvent.click(submit())

    await waitFor(() => expect(moveMoneyMutate).toHaveBeenCalled())
    expect(moveMoneyMutate).toHaveBeenCalledWith(expect.objectContaining({ amount: 60 }))
  })

  it('says what is wrong when the text is not an amount', () => {
    const amount = setup()
    fireEvent.change(amount, { target: { value: 'lunch' } })
    fireEvent.click(submit())

    expect(screen.getByText(/isn’t an amount/)).toBeInTheDocument()
    expect(moveMoneyMutate).not.toHaveBeenCalled()
  })

  it('still refuses zero, in its own words', () => {
    const amount = setup()
    fireEvent.change(amount, { target: { value: '0' } })
    fireEvent.click(submit())

    expect(screen.getByText('Enter an amount greater than zero')).toBeInTheDocument()
    expect(moveMoneyMutate).not.toHaveBeenCalled()
  })
})
