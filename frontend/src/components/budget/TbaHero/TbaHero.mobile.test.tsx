/**
 * The Ready to Assign row on a phone: the figure, the overspent chip, Assign
 * and Tools — one row. Last month and the move history leave it for the Tools
 * sheet (BudgetFilterBar's mobile branch), so the first category starts a row
 * below the month instead of a third of the screen down.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BudgetMonth } from '../../../types'
import { useUIStore } from '../../../stores/uiStore'

vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({
    data: {
      to_be_assigned: 1240,
      total_overspent: 86,
      overspent_count: 2,
      overspent_last_month: [{ category_id: 'c1', amount: 40 }],
    } as unknown as BudgetMonth,
  }),
}))
vi.mock('../../../api/categories', () => ({ useCategories: () => ({ data: [] }) }))
vi.mock('../../../api/budgetFilters', () => ({ useBudgetFilters: () => ({ data: [] }) }))
vi.mock('../../../api/budgetViews', () => ({ useBudgetViews: () => ({ data: [] }) }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => true }))
vi.mock('../../../hooks/useHistoryDismissable', () => ({ useHistoryDismissable: () => {} }))
vi.mock('../AssignDropdown/AssignDropdown', () => ({
  AssignDropdown: () => null,
  AssignDropdownContent: () => null,
}))
vi.mock('../AssignPreviewModal/AssignPreviewModal', () => ({ AssignPreviewModal: () => null }))
vi.mock('./CoverOverspentModal', () => ({ CoverOverspentModal: () => null }))
vi.mock('./TbaDrawer', () => ({ TbaDrawer: () => null }))

import { TbaHero } from './TbaHero'

beforeEach(() => {
  useUIStore.setState({
    activeQuickFilter: null,
    activeFilterId: null,
    activeViewId: null,
    categorySearch: '',
    budgetToolsOpen: false,
  })
})

describe('TbaHero on a phone', () => {
  it('keeps the overspent chip, says "over", and opens Tools from the row', () => {
    render(<TbaHero budgetId="b1" month="2026-10-01" />)
    expect(screen.getByRole('button', { name: /over$/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Budget tools' }))
    expect(useUIStore.getState().budgetToolsOpen).toBe(true)
  })

  it('moves last month and the move history into the Tools sheet', () => {
    render(<TbaHero budgetId="b1" month="2026-10-01" />)
    expect(screen.queryByText(/overspent last month/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Money moved this month' })).toBeNull()
  })

  it('says on the Tools button when the grid is narrowed', () => {
    useUIStore.setState({ categorySearch: 'groc' })
    render(<TbaHero budgetId="b1" month="2026-10-01" />)
    expect(screen.getByRole('button', { name: 'Budget tools, a filter is on' })).toBeInTheDocument()
  })
})
