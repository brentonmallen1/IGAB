/**
 * What the budget bar's one filter control offers.
 *
 * The bar drew a button per choice and grew with the number of saved filters;
 * the pixel half of why that had to stop is measured in headless Chrome
 * (`BudgetFilterBar` renders a fixed-width chip), and this is the rule that
 * decides what the chip says and what its list holds.
 */
import { describe, expect, it } from 'vitest'
import { choiceValue, filterMenu, parseChoice } from './budgetFilterMenu'
import { ALL_QUICK_FILTERS, type QuickFilter } from '../../stores/uiStore'

const NO_COUNTS: Record<QuickFilter, number> = {
  overspent: 0,
  underfunded: 0,
  pending: 0,
  'money-available': 0,
  overfunded: 0,
}

const saved = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `f${i}`, name: `Filter ${i}` }))

function menu(over: Partial<Parameters<typeof filterMenu>[0]> = {}) {
  return filterMenu({
    quickFilterOrder: ALL_QUICK_FILTERS,
    counts: NO_COUNTS,
    saved: [],
    activeQuickFilter: null,
    activeFilterId: null,
    ...over,
  })
}

const labels = (m: ReturnType<typeof filterMenu>, group: string) =>
  m.groups.find((g) => g.label === group)!.options.map((o) => o.label)

describe('the values the control round-trips', () => {
  it('carries each kind of choice through a select value', () => {
    expect(parseChoice(choiceValue({ kind: 'all' }))).toEqual({ kind: 'all' })
    expect(parseChoice(choiceValue({ kind: 'quick', filter: 'money-available' }))).toEqual({
      kind: 'quick',
      filter: 'money-available',
    })
    expect(parseChoice(choiceValue({ kind: 'saved', id: 'abc-123' }))).toEqual({
      kind: 'saved',
      id: 'abc-123',
    })
  })

  it('reads an empty value as no filter', () => {
    // What the placeholder option carries.
    expect(parseChoice('')).toEqual({ kind: 'all' })
  })
})

describe('which quick filters the list offers', () => {
  it('leaves out the ones with nothing in them', () => {
    // Same rule the chips had: a filter that would empty the grid is noise.
    const m = menu({ counts: { ...NO_COUNTS, overspent: 3 } })
    expect(labels(m, 'By status')).toEqual(['Overspent (3)'])
  })

  it('keeps the chosen one even at zero', () => {
    // The chips dropped it, which left the grid narrowed with nothing on
    // screen saying why — and a select whose value has no option reads blank.
    const m = menu({ activeQuickFilter: 'overspent' })
    expect(labels(m, 'By status')).toEqual(['Overspent (0)'])
    expect(m.value).toBe('quick:overspent')
  })

  it('offers them in the order the user arranged', () => {
    // Manage Filters reorders these; the list must not re-sort them.
    const counts = { ...NO_COUNTS, overspent: 1, overfunded: 2 }
    const m = menu({ quickFilterOrder: ['overfunded', 'overspent'], counts })
    expect(labels(m, 'By status')).toEqual(['Overfunded (2)', 'Overspent (1)'])
  })
})

describe('which saved filters the list offers', () => {
  it('offers every one of them, however many are saved', () => {
    // The point of the control: 25 filters cost the bar no width at all.
    expect(labels(menu({ saved: saved(25) }), 'Saved filters')).toHaveLength(25)
  })

  it('names the chosen one as the chip value', () => {
    expect(menu({ saved: saved(10), activeFilterId: 'f7' }).value).toBe('saved:f7')
  })

  it('falls back to no filter for an id this budget does not have', () => {
    // A filter deleted in another tab, or one persisted from another budget.
    // The grid is not narrowed by a filter that does not exist, so the chip
    // must not claim it is.
    expect(menu({ saved: saved(3), activeFilterId: 'gone' }).value).toBe('')
  })
})

describe('the overspent marker', () => {
  it('shows the count when the chip is not already naming it', () => {
    expect(menu({ counts: { ...NO_COUNTS, overspent: 4 } }).attention).toBe(4)
    expect(
      menu({ counts: { ...NO_COUNTS, overspent: 4 }, saved: saved(1), activeFilterId: 'f0' })
        .attention
    ).toBe(4)
  })

  it('goes quiet once the chip reads Overspent', () => {
    const m = menu({ counts: { ...NO_COUNTS, overspent: 4 }, activeQuickFilter: 'overspent' })
    expect(m.attention).toBe(0)
  })

  it('is absent when nothing is overspent', () => {
    expect(menu().attention).toBe(0)
  })
})
