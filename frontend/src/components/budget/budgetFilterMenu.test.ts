/**
 * What the budget bar's two controls offer.
 *
 * Pinned statuses are buttons; the other statuses and the saved filters are a
 * dropdown. The pixel half of why
 * the button row is safe — a footprint that does not move with the budget's
 * state — is measured in headless Chrome against the built stylesheet; this is
 * the rule half, which decides what renders and what it says.
 */
import { describe, expect, it } from 'vitest'
import {
  choiceValue,
  filterMenu,
  parseChoice,
  quickFilterCounts,
  quickFilterMatches,
  splitStatuses,
  statusButtons,
} from './budgetFilterMenu'
import { ALL_QUICK_FILTERS, type QuickFilter } from '../../stores/uiStore'
import type { TargetStatus } from '../../types'

const NO_COUNTS: Record<QuickFilter, number> = {
  overspent: 0,
  underfunded: 0,
  pending: 0,
  'money-available': 0,
  overfunded: 0,
  'spent-past-target': 0,
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
  it('always offers every status, whatever the budget is doing', () => {
    // THE rule. The old row dropped a status whose count hit zero, so the bar
    // got narrower as the budget got healthier and the register slid up the
    // page under it. Nothing here may depend on a count.
    expect(buttons()).toHaveLength(ALL_QUICK_FILTERS.length)
    expect(buttons({ counts: { ...NO_COUNTS, overspent: 3 } })).toHaveLength(
      ALL_QUICK_FILTERS.length
    )
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

  it('carries a status chosen from the menu', () => {
    expect(parseChoice(choiceValue({ kind: 'status', filter: 'spent-past-target' }))).toEqual({
      kind: 'status',
      filter: 'spent-past-target',
    })
  })

  it('reads a status this build does not know as no filter', () => {
    expect(parseChoice('status:retired-status')).toEqual({ kind: 'all' })
  })
})

describe('which status goes where', () => {
  it('puts each status in exactly one of the bar and the menu', () => {
    // A status in both would put its count on screen twice.
    const { bar, menu: rest } = splitStatuses(buttons(), ['overspent', 'underfunded'])
    expect(bar.map((s) => s.filter)).toEqual(['overspent', 'underfunded'])
    expect([...bar, ...rest].map((s) => s.filter).sort()).toEqual([...ALL_QUICK_FILTERS].sort())
  })

  it('keeps a pinned status on the bar at zero', () => {
    // The footprint rule: the bar's width may not move with the budget.
    const { bar } = splitStatuses(buttons(), ['overspent'])
    expect(bar).toHaveLength(1)
    expect(bar[0].disabled).toBe(true)
  })

  it('draws no buttons when nothing is pinned', () => {
    const { bar, menu: rest } = splitStatuses(buttons(), [])
    expect(bar).toEqual([])
    expect(rest).toHaveLength(ALL_QUICK_FILTERS.length)
  })
})

describe('what a status matches', () => {
  const row = (available: number, target_status: TargetStatus | null) => ({
    available,
    target_status,
  })

  it('reads overfunded and spent past target from the served status, never from figures', () => {
    // Target 100, 130 assigned to cover 130 spent, nothing left: the
    // Overfunded filter used to list this beside an Available of zero.
    const covered = { available: 0, target_status: 'spent_past_target' as const }
    expect(quickFilterMatches('overfunded', covered)).toBe(false)
    expect(quickFilterMatches('spent-past-target', covered)).toBe(true)
    const surplus = { available: 20, target_status: 'overfunded' as const }
    expect(quickFilterMatches('overfunded', surplus)).toBe(true)
    expect(quickFilterMatches('spent-past-target', surplus)).toBe(false)
  })

  it('counts with the same function the grid filters by', () => {
    const balances = [
      row(-5, null),
      row(0, 'spent_past_target'),
      row(20, 'overfunded'),
      row(10, 'underfunded'),
    ]
    const counts = quickFilterCounts(balances)
    for (const filter of ALL_QUICK_FILTERS) {
      expect(counts[filter]).toBe(balances.filter((b) => quickFilterMatches(filter, b)).length)
    }
    expect(counts).toMatchObject({
      overspent: 1,
      'money-available': 2,
      overfunded: 1,
      'spent-past-target': 1,
      underfunded: 1,
    })
  })

  it('matches nothing for a category with no balance row', () => {
    for (const filter of ALL_QUICK_FILTERS) {
      expect(quickFilterMatches(filter, undefined)).toBe(false)
    }
  })
})

describe('what the dropdown holds', () => {
  it('offers every saved filter, however many are saved', () => {
    // Unbounded is fine here and was not fine as buttons: a long list inside a
    // menu costs no width at all.
    expect(labels(menu({ saved: saved(20) }), 'Saved filters')).toHaveLength(20)
  })

  it('offers only the statuses it was handed — the ones not on the bar', () => {
    // Two readings of the overspent count, free to disagree the moment one is
    // computed from a different list. There is one.
    const { menu: rest } = splitStatuses(buttons({ counts: { ...NO_COUNTS, pending: 3 } }), [
      'overspent',
      'underfunded',
    ])
    const m = menu({ saved: saved(2), statuses: rest })
    expect(labels(m, 'Status')).toEqual([
      'Pending (3)',
      'Money Available (0)',
      'Overfunded (0)',
      'Spent Past Target (0)',
    ])
    expect(menu({ saved: saved(2) }).groups.find((g) => g.label === 'Status')!.options).toEqual([])
  })

  it('names a status chosen from it as the chip value', () => {
    const { menu: rest } = splitStatuses(buttons({ activeQuickFilter: 'pending' }), ['overspent'])
    expect(menu({ statuses: rest }).value).toBe('status:pending')
  })

  it('stays at rest while a pinned status is on', () => {
    // The button says it; the chip lighting up too would be a second reading.
    const { menu: rest } = splitStatuses(buttons({ activeQuickFilter: 'overspent' }), ['overspent'])
    expect(menu({ statuses: rest }).value).toBe('')
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
