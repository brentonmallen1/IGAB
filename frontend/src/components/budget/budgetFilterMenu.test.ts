/**
 * What the budget bar's two controls offer.
 *
 * Statuses are buttons and saved filters are a dropdown. The pixel half of why
 * the button row is safe — a footprint that does not move with the budget's
 * state — is measured in headless Chrome against the built stylesheet; this is
 * the rule half, which decides what renders and what it says.
 */
import { describe, expect, it } from 'vitest'
import { choiceValue, filterMenu, parseChoice, statusButtons } from './budgetFilterMenu'
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

function buttons(over: Partial<Parameters<typeof statusButtons>[0]> = {}) {
  return statusButtons({
    quickFilterOrder: ALL_QUICK_FILTERS,
    counts: NO_COUNTS,
    activeQuickFilter: null,
    ...over,
  })
}

function menu(over: Partial<Parameters<typeof filterMenu>[0]> = {}) {
  return filterMenu({ saved: [], activeFilterId: null, ...over })
}

const labels = (m: ReturnType<typeof filterMenu>, group: string) =>
  m.groups.find((g) => g.label === group)!.options.map((o) => o.label)

describe('the status buttons', () => {
  it('always draws all five, whatever the budget is doing', () => {
    // THE rule. The old row dropped a status whose count hit zero, so the bar
    // got narrower as the budget got healthier and the register slid up the
    // page under it. Nothing here may depend on a count.
    expect(buttons()).toHaveLength(5)
    expect(buttons({ counts: { ...NO_COUNTS, overspent: 3 } })).toHaveLength(5)
  })

  it('disables the empty ones instead of removing them', () => {
    const [overspent, underfunded] = buttons({ counts: { ...NO_COUNTS, overspent: 3 } })
    expect(overspent.disabled).toBe(false)
    expect(underfunded.disabled).toBe(true)
  })

  it('never disables the active one, even at zero', () => {
    // A filter that empties its own list still has to say what it is doing, or
    // the grid is narrowed with nothing on screen explaining it.
    const [overspent] = buttons({ activeQuickFilter: 'overspent' })
    expect(overspent.count).toBe(0)
    expect(overspent.disabled).toBe(false)
    expect(overspent.active).toBe(true)
  })

  it('clamps the count so a third digit cannot widen the slot', () => {
    const [overspent] = buttons({ counts: { ...NO_COUNTS, overspent: 250 } })
    expect(overspent.countLabel).toBe('99+')
    // The exact figure survives for the tooltip and screen readers.
    expect(overspent.count).toBe(250)
  })

  it('shows small counts exactly', () => {
    expect(buttons({ counts: { ...NO_COUNTS, overspent: 99 } })[0].countLabel).toBe('99')
    expect(buttons()[0].countLabel).toBe('0')
  })

  it('offers them in the order the user arranged', () => {
    const order: QuickFilter[] = ['pending', 'overspent', 'underfunded']
    expect(buttons({ quickFilterOrder: order }).map((b) => b.filter)).toEqual(order)
  })

  it('takes its tones from the shared variant map', () => {
    const byFilter = Object.fromEntries(buttons().map((b) => [b.filter, b.variant]))
    expect(byFilter.overspent).toBe('negative')
    expect(byFilter.underfunded).toBe('warning')
    // Pending is underfunded before its funding day — never a colour that asks
    // to be acted on today.
    expect(byFilter.pending).toBe('neutral')
  })
})

describe('the values the dropdown round-trips', () => {
  it('carries a saved choice through a select value', () => {
    expect(parseChoice(choiceValue({ kind: 'all' }))).toEqual({ kind: 'all' })
    expect(parseChoice(choiceValue({ kind: 'saved', id: 'abc-123' }))).toEqual({
      kind: 'saved',
      id: 'abc-123',
    })
  })

  it('reads an empty value as no filter', () => {
    expect(parseChoice('')).toEqual({ kind: 'all' })
  })
})

describe('what the dropdown holds', () => {
  it('offers every saved filter, however many are saved', () => {
    // Unbounded is fine here and was not fine as buttons: a long list inside a
    // menu costs no width at all.
    expect(labels(menu({ saved: saved(20) }), 'Saved filters')).toHaveLength(20)
  })

  it('offers statuses nowhere — they are buttons now', () => {
    // Two readings of the overspent count, free to disagree the moment one is
    // computed from a different list. There is one.
    const m = menu({ saved: saved(2) })
    expect(m.groups.map((g) => g.label)).toEqual(['Saved filters'])
  })

  it('names the chosen filter as the chip value', () => {
    expect(menu({ saved: saved(3), activeFilterId: 'f1' }).value).toBe('saved:f1')
  })

  it('falls back to no filter for an id this budget does not have', () => {
    // Another budget's, or one deleted in another tab. Until the bar
    // self-heals it, the chip must read "All categories" rather than blank —
    // the grid is not narrowed by a filter that does not exist.
    expect(menu({ saved: saved(2), activeFilterId: 'gone' }).value).toBe('')
  })
})
