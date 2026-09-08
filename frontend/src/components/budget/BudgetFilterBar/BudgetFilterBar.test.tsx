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
 * Statuses came back as buttons, because five fixed things you reach for by
 * eye do not belong behind a menu. The footprint rule did not go away with
 * them — it moved into the markup these tests pin: five buttons always, an
 * empty one disabled rather than removed, and saved filters still spending one
 * control however many there are.
 *
 * jsdom has no layout, so this cannot assert those pixels — see the
 * `css-layout-needs-a-browser` rule. That half is measured in headless Chrome
 * against the built stylesheet when the CSS changes; the numbers are in the
 * commit that brought the buttons back. `budgetFilterMenu.test.ts` covers the
 * rule behind what renders.
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

  it('offers no status in the list — those are buttons', () => {
    renderBar(overspent(3))
    const options = [...filterSelect().querySelectorAll('option')].map((o) => o.value)
    expect(options.some((v) => v.startsWith('quick:'))).toBe(false)
  })

  it('clears an active status when a saved filter is chosen', () => {
    // The store clears either selection when the other is set, so the buttons
    // and the list remain one choice wearing two controls.
    savedFilters = [{ id: 'f0', name: 'Bills' }]
    useUIStore.setState({ activeQuickFilter: 'overspent' })
    renderBar(overspent(3))

    fireEvent.change(filterSelect(), { target: { value: 'saved:f0' } })
    expect(useUIStore.getState().activeFilterId).toBe('f0')
    expect(useUIStore.getState().activeQuickFilter).toBeNull()
  })
})

const statusBtn = (name: string) =>
  screen.getByRole('button', { name: new RegExp(`^${name}`) }) as HTMLButtonElement

describe('the status buttons', () => {
  it('draws all five whether or not the budget has anything in them', () => {
    // The footprint rule, in markup. A row that sheds a button as a count
    // reaches zero is a row that gets narrower as the budget gets healthier.
    renderBar()
    for (const label of ['Overspent', 'Underfunded', 'Pending', 'Money Available', 'Overfunded']) {
      expect(statusBtn(label)).toBeTruthy()
    }
  })

  it('disables an empty status instead of dropping it', () => {
    renderBar(overspent(3))
    expect(statusBtn('Overspent').disabled).toBe(false)
    expect(statusBtn('Underfunded').disabled).toBe(true)
  })

  it('says the count out loud, next to the label', () => {
    renderBar(overspent(3))
    expect(statusBtn('Overspent').textContent).toContain('3')
  })

  it('applies and clears the status on click', () => {
    renderBar(overspent(3))
    fireEvent.click(statusBtn('Overspent'))
    expect(useUIStore.getState().activeQuickFilter).toBe('overspent')
    fireEvent.click(statusBtn('Overspent'))
    expect(useUIStore.getState().activeQuickFilter).toBeNull()
  })

  it('stays clickable while it is the active one at zero', () => {
    useUIStore.setState({ activeQuickFilter: 'overspent' })
    renderBar()
    expect(statusBtn('Overspent').disabled).toBe(false)
    expect(statusBtn('Overspent').getAttribute('aria-pressed')).toBe('true')
  })
})
