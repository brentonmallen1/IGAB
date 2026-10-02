import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BudgetTable } from './BudgetTable'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { makeCategory, makeCategoryGroup } from '../../../test-utils/factories'
import type { CategoryBalance } from '../../../types'

/**
 * Interest & fees against the Overspent chip and its filter.
 *
 * Red, it is in the served `total_overspent`, the hero's count and Cover
 * Overspent (all server-side, over every non-income envelope). The filter
 * bar's chip counted grid rows only, and Interest & fees is drawn in the
 * Credit cards section rather than the grid — so the chip read one fewer than
 * the red rows on the page. This mounts the real table and reads what it
 * hands the chip and the section.
 */

const chip = vi.hoisted(() => ({ balances: [] as CategoryBalance[] }))
const section = vi.hoisted(() => ({
  rowMatch: undefined as ((categoryId: string) => boolean) | null | undefined,
}))
const data = vi.hoisted(() => ({
  cards: [{ account_id: 'acct-visa' }] as unknown[],
}))

const groups = [
  makeCategoryGroup({ id: 'g-bills', name: 'Bills' }),
  makeCategoryGroup({ id: 'g-cards', name: 'Credit Card Payments', is_card_only: true }),
]
const rent = makeCategory({ id: 'rent', name: 'Rent', category_group_id: 'g-bills' })
const groceries = makeCategory({ id: 'groceries', name: 'Groceries', category_group_id: 'g-bills' })
const visa = makeCategory({
  id: 'visa-env',
  name: 'Sapphire Visa',
  category_group_id: 'g-cards',
  linked_account_id: 'acct-visa',
  in_card_section: true,
})
const interest = makeCategory({
  id: 'interest',
  name: 'Interest & fees',
  category_group_id: 'g-cards',
  in_card_section: true,
})
const balances = [
  { category_id: 'rent', available: -40 },
  { category_id: 'groceries', available: 25 },
  // The card's own envelope, red: the cards band says that, as card debt.
  { category_id: 'visa-env', available: -60 },
  { category_id: 'interest', available: -15 },
]

vi.mock('../../../api/categories', () => ({
  useCategoryGroups: () => ({ data: groups, isLoading: false }),
  useCategories: () => ({ data: [rent, groceries, visa, interest], isLoading: false }),
  useCreateCategoryGroup: () => ({ mutate: vi.fn() }),
  useReorderCategoryGroups: () => ({ mutate: vi.fn() }),
  useDeleteCategories: () => ({ mutateAsync: vi.fn() }),
  useUpdateCategory: () => ({ mutate: vi.fn() }),
  deletePreviewOptions: () => ({ queryKey: ['noop'], queryFn: async () => ({}) }),
}))
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({
    data: { category_balances: balances, cards: data.cards },
    isLoading: false,
  }),
}))
vi.mock('../../../api/budgetFilters', () => ({ useBudgetFilters: () => ({ data: [] }) }))
vi.mock('../../../api/budgetViews', () => ({ useBudgetViews: () => ({ data: [] }) }))
vi.mock('../ArchivedCategoriesModal/ArchivedCategoriesModal', () => ({
  ArchivedCategoriesModal: () => null,
}))
vi.mock('../CategoryGroupRow/CategoryGroupRow', () => ({ CategoryGroupRow: () => null }))
vi.mock('../BudgetFilterBar/BudgetFilterBar', () => ({
  BudgetFilterBar: ({ categoryBalances }: { categoryBalances: CategoryBalance[] }) => {
    chip.balances = categoryBalances
    return null
  },
}))
vi.mock('../CreditCardsSection/CreditCardsSection', () => ({
  CreditCardsSection: ({ rowMatch }: { rowMatch?: ((categoryId: string) => boolean) | null }) => {
    section.rowMatch = rowMatch
    return null
  },
}))

function mount() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <BudgetTable />
    </QueryClientProvider>
  )
}

/** The chip's own arithmetic (`BudgetFilterBar` counts), over what it is handed. */
const overspentChip = () => chip.balances.filter((b) => (b.available ?? 0) < 0).length

beforeEach(() => {
  data.cards = [{ account_id: 'acct-visa' }]
  section.rowMatch = undefined
  useAppStore.setState({ currentBudgetId: 'b1', selectedMonth: '2026-08-01' })
  useUIStore.setState({
    activeFilterId: null,
    activeViewId: null,
    activeQuickFilter: null,
    categorySearch: '',
    collapsedGroups: new Set(),
  })
})

describe('Interest & fees and the Overspent chip', () => {
  it('a red Interest & fees is counted by the Overspent chip and shows under its filter', () => {
    mount()
    // Rent and Interest & fees. This card serves no envelope, so it adds no
    // row; one that does is counted (budgetGroups.test.ts).
    expect(chip.balances.map((b) => b.category_id).sort()).toEqual([
      'groceries',
      'interest',
      'rent',
    ])
    expect(overspentChip()).toBe(2)
    // No filter active: the section's fold decides.
    expect(section.rowMatch).toBeNull()

    useUIStore.setState({ activeQuickFilter: 'overspent' })
    mount()
    expect(section.rowMatch?.('interest')).toBe(true)
  })

  it('a funded Interest & fees is hidden by the Overspent filter, like a funded grid row', () => {
    useUIStore.setState({ activeQuickFilter: 'money-available' })
    mount()
    expect(section.rowMatch?.('interest')).toBe(false)
  })

  it('search reaches it by name', () => {
    useUIStore.setState({ categorySearch: 'interest' })
    mount()
    expect(section.rowMatch?.('interest')).toBe(true)
    useUIStore.setState({ categorySearch: 'rent' })
    mount()
    expect(section.rowMatch?.('interest')).toBe(false)
  })

  it('with no card the section is not drawn, so the chip does not count it', () => {
    data.cards = []
    mount()
    expect(chip.balances.map((b) => b.category_id)).not.toContain('interest')
    expect(overspentChip()).toBe(1)
  })
})
