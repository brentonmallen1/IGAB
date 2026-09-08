/**
 * The bar's footprint must not depend on how much is saved in it.
 *
 * It drew a button per choice — `All`, a quick filter per non-zero count, one
 * per saved filter — and the grid offsets its sticky column header by this
 * bar's *measured height*, so every filter someone saved pushed the register
 * further down the page. Bounding the buttons at three plus a picker helped
 * and did not fix it: the row still changed width as counts came and went,
 * and on a phone it was several rows deep before anyone saved anything.
 *
 * jsdom has no layout, so this cannot assert those pixels — see the
 * `css-layout-needs-a-browser` rule. What it CAN pin is the markup contract
 * the fixed width rests on: one control, whatever is saved.
 * `budgetFilterMenu.test.ts` covers what that control offers.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BudgetFilterBar } from './BudgetFilterBar'
import { useUIStore } from '../../../stores/uiStore'
import type { CategoryBalance } from '../../../types'

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

/** Only `available` and `target_status` are read, and only to count. */
const overspent = (n: number) =>
  Array.from({ length: n }, () => ({ available: -1 })) as unknown as CategoryBalance[]

function renderBar(balances: CategoryBalance[] = []) {
  return render(<BudgetFilterBar budgetId="b1" categoryBalances={balances} />, { wrapper })
}

const filterSelect = () => screen.getByLabelText('Filter categories') as HTMLSelectElement

beforeEach(() => {
  savedFilters = []
  useUIStore.setState({ activeFilterId: null, activeQuickFilter: null, categorySearch: '' })
})

describe('the bar with many saved filters', () => {
  it('spends one control on them however many there are', () => {
    savedFilters = Array.from({ length: 25 }, (_, i) => ({ id: `f${i}`, name: `Filter ${i}` }))
    renderBar()

    // No button is named after a saved filter — that row is what grew.
    const named = screen.getAllByRole('button').filter((b) => b.textContent?.startsWith('Filter '))
    expect(named).toEqual([])
    // And every one of them is still reachable: 25 + the All option.
    expect(filterSelect().querySelectorAll('option')).toHaveLength(26)
  })

  it('applies the filter chosen from the list', () => {
    savedFilters = [{ id: 'f0', name: 'Bills' }]
    renderBar()

    fireEvent.change(filterSelect(), { target: { value: 'saved:f0' } })
    expect(useUIStore.getState().activeFilterId).toBe('f0')
  })

  it('clears both selections when the list goes back to All', () => {
    savedFilters = [{ id: 'f0', name: 'Bills' }]
    useUIStore.setState({ activeFilterId: 'f0' })
    renderBar()

    fireEvent.change(filterSelect(), { target: { value: '' } })
    expect(useUIStore.getState().activeFilterId).toBeNull()
    expect(useUIStore.getState().activeQuickFilter).toBeNull()
  })

  it('applies a quick filter from the same list', () => {
    // The store clears either selection when the other is set, so these were
    // never two independent controls to begin with.
    renderBar(overspent(3))
    fireEvent.change(filterSelect(), { target: { value: 'quick:overspent' } })
    expect(useUIStore.getState().activeQuickFilter).toBe('overspent')
  })
})

describe('what the bar still says out loud', () => {
  it('marks overspent money the chip is not already naming', () => {
    renderBar(overspent(3))
    expect(screen.getByText('3 overspent categories')).toBeTruthy()
  })

  it('drops the marker once the filter itself says Overspent', () => {
    useUIStore.setState({ activeQuickFilter: 'overspent' })
    renderBar(overspent(3))
    expect(screen.queryByText('3 overspent categories')).toBeNull()
  })

  it('says nothing when nothing is overspent', () => {
    renderBar()
    expect(screen.queryByText(/overspent/)).toBeNull()
  })
})
