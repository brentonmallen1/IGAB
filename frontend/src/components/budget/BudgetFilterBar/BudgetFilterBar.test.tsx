/**
 * The bar's height must not grow with the number of saved filters.
 *
 * It drew one button per filter, and the grid offsets its sticky column header
 * by this bar's *measured height* — so every filter someone saved pushed the
 * register further down the page. Measured in headless Chrome against the real
 * stylesheet, 25 filters cost an extra row at 1440px (35 → 65px) and two at
 * 900px (65 → 119px); bounded, the height is flat at every width.
 *
 * jsdom has no layout, so this cannot assert those pixels — see the
 * `css-layout-needs-a-browser` rule. What it CAN pin is the thing that decides
 * them: however many filters are saved, the bar renders a bounded number of
 * chips. `budgetFilterChips.test.ts` covers which ones; this covers that the
 * bar actually asks.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BudgetFilterBar } from './BudgetFilterBar'
import { PINNED_FILTER_COUNT } from '../budgetFilterChips'
import { useUIStore } from '../../../stores/uiStore'

let savedFilters: { id: string; name: string }[] = []

vi.mock('../../../api/budgetFilters', () => ({
  useBudgetFilters: () => ({ data: savedFilters }),
}))
vi.mock('../../../api/budgetViews', () => ({
  useBudgetViews: () => ({ data: [] }),
}))

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function renderBar() {
  return render(<BudgetFilterBar budgetId="b1" categoryBalances={[]} />, { wrapper })
}

/** The filter chips, which are the buttons named after a saved filter — not
 *  `All`, not a quick filter, not the density or menu controls. */
function filterChipNames(): string[] {
  return screen
    .getAllByRole('button')
    .map((b) => b.textContent ?? '')
    .filter((label) => label.startsWith('Filter '))
}

beforeEach(() => {
  savedFilters = []
  useUIStore.setState({ activeFilterId: null, activeQuickFilter: null, categorySearch: '' })
})

describe('the bar with many saved filters', () => {
  it('draws them all while there are few', () => {
    savedFilters = [
      { id: 'f0', name: 'Filter 0' },
      { id: 'f1', name: 'Filter 1' },
    ]
    renderBar()
    expect(filterChipNames()).toEqual(['Filter 0', 'Filter 1'])
    expect(screen.queryByLabelText('More saved filters')).toBeNull()
  })

  it('bounds the chips and offers the rest behind one picker', () => {
    savedFilters = Array.from({ length: 25 }, (_, i) => ({ id: `f${i}`, name: `Filter ${i}` }))
    renderBar()

    expect(filterChipNames()).toHaveLength(PINNED_FILTER_COUNT)
    const picker = screen.getByLabelText('More saved filters')
    // Every filter is still reachable — bounded, not hidden.
    expect(picker.querySelectorAll('option')).toHaveLength(25 - PINNED_FILTER_COUNT + 1)
  })

  it('keeps the active filter on the bar when it is not pinned', () => {
    savedFilters = Array.from({ length: 25 }, (_, i) => ({ id: `f${i}`, name: `Filter ${i}` }))
    useUIStore.setState({ activeFilterId: 'f9' })
    renderBar()

    // The bar's job is to say what is narrowing the grid.
    expect(filterChipNames()).toContain('Filter 9')
    expect(filterChipNames()).toHaveLength(PINNED_FILTER_COUNT + 1)
  })
})
