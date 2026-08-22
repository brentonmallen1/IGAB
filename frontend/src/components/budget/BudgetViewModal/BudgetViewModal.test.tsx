/**
 * The editor's job is to make a view's arrangement legible before it is
 * saved. Two things went wrong in the field: "Hide unassigned categories"
 * did not visibly claim the unassigned rows (so it read as broken), and
 * mounting the editor before the views query resolved would initialise an
 * empty form over a real view — saving that wipes it.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const viewsState = vi.hoisted(() => ({ current: undefined as unknown }))
const updateMock = vi.hoisted(() => vi.fn())

vi.mock('../../../api/categories', () => ({
  useCategoryGroups: () => ({
    data: [{ id: 'g1', name: 'Everyday' }],
  }),
  useCategories: () => ({
    data: [
      { id: 'c-rent', name: 'Rent', category_group_id: 'g1' },
      { id: 'c-dining', name: 'Dining Out', category_group_id: 'g1' },
      { id: 'c-fun', name: 'Fun Money', category_group_id: 'g1' },
    ],
  }),
}))
vi.mock('../../../api/budgetViews', () => ({
  useBudgetViews: () => ({ data: viewsState.current }),
  useCreateBudgetView: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateBudgetView: () => ({ mutateAsync: updateMock, isPending: false }),
  useDeleteBudgetView: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

import { BudgetViewModal } from './BudgetViewModal'

const SAVED_VIEW = {
  id: 'v1',
  name: 'Need / Want',
  hide_unassigned: false,
  groups: [{ id: 'vg1', name: 'Need' }],
  placements: [
    { category_id: 'c-rent', group_id: 'vg1', is_hidden: false },
    { category_id: 'c-dining', group_id: null, is_hidden: true },
  ],
}

function hideBoxFor(category: string) {
  const row = screen.getByLabelText(`Group for ${category}`).closest('.view-editor__row')!
  return within(row as HTMLElement).getByRole('checkbox') as HTMLInputElement
}

beforeEach(() => {
  viewsState.current = [SAVED_VIEW]
  updateMock.mockReset()
})

describe('BudgetViewModal', () => {
  it('does not mount the form over a view that has not loaded yet', () => {
    viewsState.current = undefined
    const { container } = render(
      <BudgetViewModal budgetId="b1" viewId="v1" onClose={() => {}} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('a new view still opens while the list is loading', () => {
    viewsState.current = undefined
    render(<BudgetViewModal budgetId="b1" viewId={null} onClose={() => {}} />)
    expect(screen.getByText('New View')).toBeInTheDocument()
  })

  describe('“Hide unassigned categories” claims the unassigned rows', () => {
    it('shows unassigned rows as hidden the moment the flag is on', () => {
      render(<BudgetViewModal budgetId="b1" viewId="v1" onClose={() => {}} />)

      const flag = screen.getByRole('checkbox', { name: /^Hide unassigned categories/ })
      expect(hideBoxFor('Fun Money').checked).toBe(false)

      fireEvent.click(flag)

      const box = hideBoxFor('Fun Money')
      expect(box.checked).toBe(true)
      expect(box.disabled).toBe(true)
    })

    it('placed rows are untouched by the flag', () => {
      render(<BudgetViewModal budgetId="b1" viewId="v1" onClose={() => {}} />)
      fireEvent.click(screen.getByRole('checkbox', { name: /^Hide unassigned categories/ }))

      const box = hideBoxFor('Rent')
      expect(box.checked).toBe(false)
      expect(box.disabled).toBe(false)
    })

    it('an individually hidden row keeps its own checkbox editable', () => {
      render(<BudgetViewModal budgetId="b1" viewId="v1" onClose={() => {}} />)
      fireEvent.click(screen.getByRole('checkbox', { name: /^Hide unassigned categories/ }))

      const box = hideBoxFor('Dining Out')
      expect(box.checked).toBe(true)
      expect(box.disabled).toBe(false)
    })

    it('turning the flag back off releases the rows', () => {
      render(<BudgetViewModal budgetId="b1" viewId="v1" onClose={() => {}} />)
      const flag = screen.getByRole('checkbox', { name: /^Hide unassigned categories/ })
      fireEvent.click(flag)
      fireEvent.click(flag)

      const box = hideBoxFor('Fun Money')
      expect(box.checked).toBe(false)
      expect(box.disabled).toBe(false)
    })
  })
})
