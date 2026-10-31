import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BudgetTable } from './BudgetTable'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'

/**
 * The phone's category search lives in the grid's column header row.
 *
 * It was moved into the Tools sheet with the rest of the bar, where it was one
 * tap further away than anything else people reach for while scrolling a
 * budget. Back in a header, it costs no height: the row is there anyway.
 */

const media = { mobile: true }
const bar = { searchOpen: undefined as boolean | undefined }

vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => media.mobile }))
vi.mock('../../../api/categories', () => ({
  useCategoryGroups: () => ({ data: [], isLoading: false }),
  useCategories: () => ({ data: [], isLoading: false }),
  useCreateCategoryGroup: () => ({ mutate: vi.fn() }),
  useReorderCategoryGroups: () => ({ mutate: vi.fn() }),
  useDeleteCategories: () => ({ mutateAsync: vi.fn() }),
  useUpdateCategory: () => ({ mutate: vi.fn() }),
  deletePreviewOptions: () => ({ queryKey: ['noop'], queryFn: async () => ({}) }),
}))
vi.mock('../ArchivedCategoriesModal/ArchivedCategoriesModal', () => ({
  ArchivedCategoriesModal: () => null,
}))
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: { category_balances: [] }, isLoading: false }),
}))
vi.mock('../../../api/budgetFilters', () => ({ useBudgetFilters: () => ({ data: [] }) }))
vi.mock('../../../api/budgetViews', () => ({ useBudgetViews: () => ({ data: [] }) }))
vi.mock('../CreditCardsSection/CreditCardsSection', () => ({ CreditCardsSection: () => null }))
vi.mock('../BudgetFilterBar/BudgetFilterBar', () => ({
  BudgetFilterBar: ({ searchOpen }: { searchOpen?: boolean }) => {
    bar.searchOpen = searchOpen
    return null
  },
}))

beforeEach(() => {
  media.mobile = true
  bar.searchOpen = undefined
  useAppStore.setState({ currentBudgetId: 'b1', selectedMonth: '2026-10-01' })
  useUIStore.setState({
    activeFilterId: null,
    activeViewId: null,
    activeQuickFilter: null,
    categorySearch: '',
    collapsedGroups: new Set(),
  })
})

function mount() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BudgetTable />
    </QueryClientProvider>
  )
}

const field = () => screen.queryByRole('searchbox', { name: /Filter categories/ })

describe('the phone column header search', () => {
  it('rests as a magnifier, and opens into the row', () => {
    mount()
    expect(field()).toBeNull()
    expect(screen.getByText('Category')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Find a category' }))
    expect(field()).toHaveFocus()
    // The row is the field now: the column label and its buttons step aside.
    expect(screen.queryByText('Category')).toBeNull()
    expect(screen.queryByRole('button', { name: /See archived/ })).toBeNull()
    // And the strip above is told, so it does not repeat the query.
    expect(bar.searchOpen).toBe(true)
  })

  it('filters as you type, and Done keeps the query', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Find a category' }))
    fireEvent.change(field()!, { target: { value: 'rent' } })
    expect(useUIStore.getState().categorySearch).toBe('rent')

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(field()).toBeNull()
    expect(useUIStore.getState().categorySearch).toBe('rent')
    expect(bar.searchOpen).toBe(false)
    // Shut with a query on, the magnifier says so.
    expect(screen.getByRole('button', { name: 'Find a category, a search is on' })).toHaveClass(
      'active'
    )
  })

  it('reopens on the query it left', () => {
    useUIStore.setState({ categorySearch: 'groc' })
    mount()
    fireEvent.click(screen.getByRole('button', { name: /Find a category/ }))
    expect(field()).toHaveValue('groc')
  })

  it('draws no magnifier on a desktop, where the bar has the field', () => {
    media.mobile = false
    mount()
    expect(screen.queryByRole('button', { name: /Find a category/ })).toBeNull()
    expect(bar.searchOpen).toBe(false)
  })
})
