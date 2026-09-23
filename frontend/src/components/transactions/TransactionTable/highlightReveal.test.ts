import { describe, expect, it } from 'vitest'
import {
  HIGHLIGHT_PAGE_BUDGET,
  holdsHighlight,
  sectionOpen,
  shouldDropSearch,
  shouldPageForHighlight,
} from './highlightReveal'

const rows = [{ id: 't1' }, { id: 't2' }]

describe('holdsHighlight', () => {
  it('is false when nothing was asked for', () => {
    expect(holdsHighlight(rows, null)).toBe(false)
    expect(holdsHighlight(rows, undefined)).toBe(false)
  })

  it('finds the row it was asked for', () => {
    expect(holdsHighlight(rows, 't2')).toBe(true)
    expect(holdsHighlight(rows, 't9')).toBe(false)
  })
})

describe('sectionOpen', () => {
  const shut = new Set(['pending'])

  it('respects the stored fold when nothing was asked for', () => {
    expect(sectionOpen(shut, 'pending', rows, null)).toBe(false)
    expect(sectionOpen(shut, 'uncategorized', rows, null)).toBe(true)
  })

  it('opens a shut section that is holding the row somebody clicked', () => {
    // Pending starts collapsed and the fold is PERSISTED, so this is the
    // common case, not the odd one: clicking a pending transaction anywhere
    // in the app used to land on a register that rendered none of it.
    // `Collapsible` draws no children while shut, so the row was not hidden
    // — it was absent, and the highlight's DOM fallback had nothing to find.
    expect(sectionOpen(shut, 'pending', rows, 't1')).toBe(true)
  })

  it('leaves other sections folded as the person left them', () => {
    const allShut = new Set(['pending', 'uncategorized', 'upcoming'])
    expect(sectionOpen(allShut, 'pending', rows, 't1')).toBe(true)
    expect(sectionOpen(allShut, 'uncategorized', [{ id: 't5' }], 't1')).toBe(false)
  })

  it('does not write the fold — it only renders around it', () => {
    // The override lasts as long as the highlight and no longer. Spending a
    // standing choice to show one row would mean refolding the section
    // afterwards, which is a worse trade than it looks.
    const stored = new Set(['pending'])
    sectionOpen(stored, 'pending', rows, 't1')
    expect([...stored]).toEqual(['pending'])
  })
})

describe('shouldDropSearch', () => {
  it('drops a search when a row is asked for by id', () => {
    expect(shouldDropSearch('coffee', 't1', null)).toBe(true)
  })

  it('leaves the search alone when nobody asked for a row', () => {
    expect(shouldDropSearch('coffee', null, null)).toBe(false)
  })

  it('drops once per arrival and never again', () => {
    // The bug this argument exists for. The highlight stays in the URL until
    // the reader selects a row, so "there is a highlight and there is a
    // search" is true again on every keystroke — and someone typing into the
    // search box after following a link watched it empty itself as they
    // typed. Worse than the stale filter it was added to fix.
    expect(shouldDropSearch('coffee', 't1', 't1')).toBe(false)
  })

  it('drops again when a different row is asked for', () => {
    // A second jump is a second arrival, even without leaving the register.
    expect(shouldDropSearch('coffee', 't2', 't1')).toBe(true)
  })

  it('does not "clear" a search that is already clear', () => {
    // The effect calling this writes to a global store, and a write that
    // changes nothing still re-renders every consumer of it — on every
    // render, forever.
    expect(shouldDropSearch('', 't1', null)).toBe(false)
    expect(shouldDropSearch('   ', 't1', null)).toBe(false)
  })
})

describe('shouldPageForHighlight', () => {
  const base = {
    highlightId: 't1' as string | null,
    isLoaded: false,
    pagesLoaded: 1,
    hasNextPage: true,
    isFetching: false,
  }

  it('pages on to find a row that is not loaded yet', () => {
    // The failure that only shows up on a real account: the register pages
    // newest-first, so a transaction from a few months back is simply not in
    // the first hundred rows. The scroll effect then looks for an index that
    // does not exist and does nothing — no error, no row, no explanation.
    expect(shouldPageForHighlight(base)).toBe(true)
  })

  it('stops the moment the row arrives', () => {
    expect(shouldPageForHighlight({ ...base, isLoaded: true })).toBe(false)
  })

  it('does nothing when nobody asked for a row', () => {
    expect(shouldPageForHighlight({ ...base, highlightId: null })).toBe(false)
  })

  it('waits for the request already in flight', () => {
    // React Query serves one page at a time; asking again mid-flight is how
    // an auto-pager turns into a request storm.
    expect(shouldPageForHighlight({ ...base, isFetching: true })).toBe(false)
  })

  it('gives up at the end of the register rather than looping', () => {
    expect(shouldPageForHighlight({ ...base, hasNextPage: false })).toBe(false)
  })

  it('gives up on a row that is not in this account at all', () => {
    // A deleted transaction, or an id from another budget. Without the cap
    // this walks the whole account one request at a time and never stops.
    expect(shouldPageForHighlight({ ...base, pagesLoaded: HIGHLIGHT_PAGE_BUDGET })).toBe(false)
  })
})
