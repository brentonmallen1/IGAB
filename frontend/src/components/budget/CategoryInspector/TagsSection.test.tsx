/**
 * The inspector's Tags section shows the savings-mode question on a savings
 * category, reading which tags are on it from the budget's tag list — the
 * category's own tags carry no system key.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeCategory } from '../../../test-utils/factories'

vi.mock('../../../api/tags', () => ({
  useTags: () => ({
    data: [
      { id: 't-sav', name: 'Savings', color_slot: 'green', system_key: 'savings' },
      {
        id: 't-lte',
        name: 'Long-term expense',
        color_slot: 'blue',
        system_key: 'long_term_expense',
      },
    ],
  }),
  useSetCategoryTags: () => ({ mutate: vi.fn() }),
  useCreateTag: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('../../../api/categories', () => ({
  useUpdateCategory: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }),
}))

import { TagsSection } from './TagsSection'

const SAVINGS = { id: 't-sav', name: 'Savings', color_slot: 'green' as const }
const LONG_TERM = { id: 't-lte', name: 'Long-term expense', color_slot: 'blue' as const }

describe('TagsSection', () => {
  it('asks how a savings category counts, with the conflict when it is also a sinking fund', () => {
    render(
      <TagsSection
        category={makeCategory({ savings_role: 'sent_out', tags: [SAVINGS, LONG_TERM] })}
        budgetId="b1"
      />
    )
    expect(
      screen.getByRole('group', { name: 'Counts as saved when money is:' })
    ).toBeInTheDocument()
    expect(screen.getByText(/it counts as savings, not as a sinking fund/)).toBeInTheDocument()
  })

  it('does not ask on a category that is not a savings category', () => {
    render(<TagsSection category={makeCategory({ tags: [LONG_TERM] })} budgetId="b1" />)
    expect(screen.queryByRole('group', { name: /Counts as saved/ })).not.toBeInTheDocument()
  })
})
