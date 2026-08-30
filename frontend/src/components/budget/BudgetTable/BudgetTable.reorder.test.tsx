import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BudgetTable } from './BudgetTable'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'

/**
 * The two things the grid and the filter bar must agree about: which list a
 * drag indexes into, and whether dragging is offered at all.
 *
 * Both were wrong in ways no pure test could reach, because both are wiring:
 * one list built from the wrong source, one gate given the wrong input. So
 * this mounts the real component and reads the payload it writes.
 */

const reorderGroups = vi.fn()
let groupsData: unknown[] = []
let viewsData: unknown[] | undefined = []

vi.mock('../../../api/categories', () => ({
  useCategoryGroups: () => ({ data: groupsData, isLoading: false }),
  useCategories: () => ({ data: [], isLoading: false }),
  useCreateCategoryGroup: () => ({ mutate: vi.fn() }),
  useReorderCategoryGroups: () => ({ mutate: reorderGroups }),
}))
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: { category_balances: [] }, isLoading: false }),
}))
vi.mock('../../../api/budgetFilters', () => ({ useBudgetFilters: () => ({ data: [] }) }))
vi.mock('../../../api/budgetViews', () => ({ useBudgetViews: () => ({ data: viewsData }) }))
vi.mock('../CreditCardsSection/CreditCardsSection', () => ({
  CreditCardsSection: () => null,
}))

// A stub standing in for the real row: one button per group that asks the
// drag api to move that group down, so the test can read what gets written
// without simulating HTML5 drag events.
vi.mock('../CategoryGroupRow/CategoryGroupRow', () => ({
  CategoryGroupRow: ({
    group,
    index,
    reorder,
  }: {
    group: { id: string; name: string }
    index: number
    reorder?: { moveBy: (i: number, d: -1 | 1) => void }
  }) => (
    <div data-testid="group-row" data-group-id={group.id}>
      {group.name}
      {reorder && (
        <button data-testid={`move-${group.name}`} onClick={() => reorder.moveBy(index, 1)}>
          move down
        </button>
      )}
    </div>
  ),
}))

function group(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    name,
    budget_id: 'b1',
    is_hidden: false,
    is_system: false,
    is_card_only: false,
    sort_order: 0,
    ...extra,
  }
}

beforeEach(() => {
  reorderGroups.mockClear()
  viewsData = []
  useAppStore.setState({ currentBudgetId: 'b1', selectedMonth: '2026-08-01' })
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

describe('group reorder wiring', () => {
  it('writes the drawn groups, not the ones it was handed', () => {
    // "Credit Card Payments" is in the group list — it is what "Show hidden"
    // reveals — but the grid never draws it, because every one of its rows
    // belongs to the cards section. It must not be in the order that gets
    // written either: built from the full list, index 0 addressed the card
    // group while the user was dragging the first row they could see.
    groupsData = [
      group('cards', 'Credit Card Payments', { is_hidden: true, is_card_only: true }),
      group('bills', 'Bills'),
      group('fun', 'Fun'),
    ]
    mount()

    expect(screen.getAllByTestId('group-row').map((r) => r.dataset.groupId)).toEqual([
      'bills',
      'fun',
    ])

    screen.getByTestId('move-Bills').click()
    expect(reorderGroups).toHaveBeenCalledWith(['fun', 'bills'])
  })

  it('still offers the handles when a card-only group is present', () => {
    // The gate this replaced compared array identity, so the mere presence of
    // a dropped group turned dragging off with nothing to explain it.
    groupsData = [
      group('cards', 'Credit Card Payments', { is_hidden: true, is_card_only: true }),
      group('bills', 'Bills'),
      group('fun', 'Fun'),
    ]
    mount()
    expect(screen.getByTestId('move-Bills')).toBeTruthy()
  })

  it('offers no handles while a filter is active, and says why once', () => {
    groupsData = [group('bills', 'Bills'), group('fun', 'Fun')]
    useUIStore.setState({ activeQuickFilter: 'overspent' })
    mount()
    expect(screen.queryByTestId('move-Bills')).toBeNull()
    expect(screen.getByText('Ordering is off while filtered')).toBeTruthy()
  })

  it('says nothing about a view the grid has not resolved yet', () => {
    // A persisted view id with the view list still loading. The grid gates on
    // the RESOLVED view, so it offers handles; the bar read the stored id and
    // announced "This view keeps its own order" over a grid that was letting
    // the user drag. Two surfaces, one rule, opposite stories.
    groupsData = [group('bills', 'Bills'), group('fun', 'Fun')]
    viewsData = undefined
    useUIStore.setState({ activeViewId: 'not-loaded-yet' })
    mount()
    expect(screen.getByTestId('move-Bills')).toBeTruthy()
    expect(screen.queryByText('This view keeps its own order')).toBeNull()
  })
})
