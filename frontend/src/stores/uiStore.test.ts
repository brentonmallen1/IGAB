import { describe, expect, it } from 'vitest'
import {
  ALL_QUICK_FILTERS,
  mergeQuickFilterOrder,
  normalizeBudgetRowMode,
  useUIStore,
} from './uiStore'

describe('mergeQuickFilterOrder', () => {
  it('a persisted order without pending gains it', () => {
    // Every existing user has an order saved from before the chip existed;
    // without this the new chip would never appear for them.
    expect(
      mergeQuickFilterOrder(['overfunded', 'overspent', 'underfunded', 'money-available'])
    ).toEqual(['overfunded', 'overspent', 'underfunded', 'money-available', 'pending'])
  })

  it('keeps a complete saved order as it is', () => {
    const saved = [...ALL_QUICK_FILTERS].reverse()
    expect(mergeQuickFilterOrder(saved)).toEqual(saved)
  })

  it('drops a filter that no longer exists and starts from the canonical order when nothing was saved', () => {
    expect(mergeQuickFilterOrder(['overspent', 'retired'])).toEqual([
      'overspent',
      'underfunded',
      'pending',
      'money-available',
      'overfunded',
    ])
    expect(mergeQuickFilterOrder(undefined)).toEqual(ALL_QUICK_FILTERS)
  })
})

describe('normalizeBudgetRowMode', () => {
  it("reads a persisted 'compressed' as dense — that is what it meant", () => {
    expect(normalizeBudgetRowMode('compressed')).toBe('dense')
  })
  it('keeps the two new modes and falls back to expanded', () => {
    expect(normalizeBudgetRowMode('compact')).toBe('compact')
    expect(normalizeBudgetRowMode('dense')).toBe('dense')
    expect(normalizeBudgetRowMode(undefined)).toBe('expanded')
    expect(normalizeBudgetRowMode('bogus')).toBe('expanded')
  })
})

describe('the account header fold', () => {
  it('survives a reload', () => {
    // A standing choice, like the budget page's group folds and its cards
    // strip: someone who works from the register should not refold the
    // header on every visit.
    const partialize = useUIStore.persist.getOptions().partialize
    expect(partialize).toBeDefined()
    const kept = partialize!({
      ...useUIStore.getState(),
      accountHeaderCollapsed: true,
    } as never) as Record<string, unknown>
    expect(kept.accountHeaderCollapsed).toBe(true)
  })

  it('starts unchosen, which is not the same as open', () => {
    // Null is what lets a phone start folded and a desktop start open
    // without either being a decision anyone made — see headerCollapse.ts.
    expect(useUIStore.getState().accountHeaderCollapsed).toBeNull()
  })

  it('takes a value rather than toggling', () => {
    // The rendered state is derived from three inputs, so "the opposite of
    // what is stored" is not reliably "the opposite of what you can see":
    // during a reconcile the header is folded whatever the store says.
    useUIStore.getState().setAccountHeaderCollapsed(true)
    expect(useUIStore.getState().accountHeaderCollapsed).toBe(true)
    useUIStore.getState().setAccountHeaderCollapsed(false)
    expect(useUIStore.getState().accountHeaderCollapsed).toBe(false)
  })
})

describe('register section folds', () => {
  const partialize = () => useUIStore.persist.getOptions().partialize!
  const merge = () => useUIStore.persist.getOptions().merge!

  it('start with pending folded — the one section that hides rows by default', () => {
    expect(useUIStore.getState().collapsedSections.has('pending')).toBe(true)
  })

  it('survive a reload, so opening pending lasts longer than the tab', () => {
    // Without this, opening Pending held until the next reload and then hid
    // the rows again — which is how a synced card payment went unseen.
    const kept = partialize()({
      ...useUIStore.getState(),
      collapsedSections: new Set(['upcoming']),
    } as never) as Record<string, unknown>
    expect(kept.collapsedSections).toEqual(['upcoming'])
  })

  it('rebuild as a Set, not the array they were stored as', () => {
    // A Set does not survive JSON; rehydrating the raw array leaves `.has`
    // undefined, which throws on the register's first render.
    const state = merge()({ collapsedSections: ['upcoming'] }, useUIStore.getState()) as {
      collapsedSections: Set<string>
    }
    expect(state.collapsedSections).toBeInstanceOf(Set)
    expect(state.collapsedSections.has('upcoming')).toBe(true)
    expect(state.collapsedSections.has('pending')).toBe(false)
  })

  it('tell "every section open" apart from "nothing saved yet"', () => {
    // Both are falsy-ish and an `?? []` fallback spells them the same way.
    // An empty array is a real choice and must not re-fold pending.
    const opened = merge()({ collapsedSections: [] }, useUIStore.getState()) as {
      collapsedSections: Set<string>
    }
    expect(opened.collapsedSections.size).toBe(0)

    const fresh = merge()({}, useUIStore.getState()) as { collapsedSections: Set<string> }
    expect(fresh.collapsedSections.has('pending')).toBe(true)
  })
})
