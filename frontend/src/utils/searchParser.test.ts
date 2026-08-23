import { describe, it, expect } from 'vitest'
import {
  parseTransactionSearch,
  hasActiveFilters,
  describeSearchChips,
  removeSearchChip,
} from './searchParser'

const EMPTY_MAP = new Map<string, string>()

// Tuesday, August 11 2026 — fixed so date-token tests are deterministic
const NOW = new Date(2026, 7, 11)

function parse(query: string) {
  return parseTransactionSearch(query, EMPTY_MAP, EMPTY_MAP, new Map(), NOW)
}

// ─── Basic filter parsing ──────────────────────────────────────────────────────

describe('is: filters', () => {
  it('parses is: unapproved', () => {
    expect(parse('is: unapproved').unapproved).toBe(true)
  })

  it('parses is: uncategorized', () => {
    expect(parse('is: uncategorized').uncategorized).toBe(true)
  })

  it('parses is: cleared', () => {
    expect(parse('is: cleared').cleared).toBe('cleared')
  })

  it('parses is: uncleared', () => {
    expect(parse('is: uncleared').cleared).toBe('uncleared')
  })

  it('parses is: pending', () => {
    expect(parse('is: pending').cleared).toBe('pending')
  })

  it('parses is: reconciled', () => {
    expect(parse('is: reconciled').cleared).toBe('reconciled')
  })

  it('parses compact is:unapproved without space', () => {
    expect(parse('is:unapproved').unapproved).toBe(true)
  })

  it('parses compact is:uncategorized without space', () => {
    expect(parse('is:uncategorized').uncategorized).toBe(true)
  })
})

describe('has: attachment filter', () => {
  it('parses has: attachment (spaced)', () => {
    expect(parse('has: attachment').hasAttachment).toBe(true)
  })

  it('parses compact has:attachment', () => {
    expect(parse('has:attachment').hasAttachment).toBe(true)
  })

  it('accepts image and receipt synonyms', () => {
    expect(parse('has:image').hasAttachment).toBe(true)
    expect(parse('has: receipt').hasAttachment).toBe(true)
  })

  it('parses NOT has: attachment as exclusion', () => {
    expect(parse('NOT has: attachment').hasAttachment).toBe(false)
    expect(parse('NOT has:attachment').hasAttachment).toBe(false)
  })

  it('combines with other filters', () => {
    const f = parse('is: unapproved has:attachment')
    expect(f.unapproved).toBe(true)
    expect(f.hasAttachment).toBe(true)
  })

  it('survives OR merging', () => {
    const f = parse('has:attachment OR is: uncategorized')
    expect(f.hasAttachment).toBe(true)
    expect(f.uncategorized).toBe(true)
    expect(f.isOrMode).toBe(true)
  })

  it('unknown has: value falls through without setting the filter', () => {
    expect(parse('has:wings').hasAttachment).toBeUndefined()
  })

  it('counts as an active filter', () => {
    expect(hasActiveFilters(parse('has:attachment'))).toBe(true)
    expect(hasActiveFilters(parse('NOT has:attachment'))).toBe(true)
  })
})

describe('text search', () => {
  it('treats unrecognized tokens as text', () => {
    expect(parse('coffee shop').text).toBe('coffee shop')
  })

  it('combines text with structured filters', () => {
    const result = parse('is: unapproved starbucks')
    expect(result.unapproved).toBe(true)
    expect(result.text).toBe('starbucks')
  })
})

describe('amount filters', () => {
  it('parses amount:>100', () => {
    expect(parse('amount:>100').amountMin).toBe(100)
  })

  it('parses amount:<50', () => {
    expect(parse('amount:<50').amountMax).toBe(50)
  })

  it('parses amount range 10-50', () => {
    const result = parse('amount:10-50')
    expect(result.amountMin).toBe(10)
    expect(result.amountMax).toBe(50)
  })

  it('parses an exact amount as a zero-width range', () => {
    const result = parse('amount: 12.34')
    expect(result.amountMin).toBe(12.34)
    expect(result.amountMax).toBe(12.34)
  })

  it('parses an exact amount in compact form, with $ and commas', () => {
    const result = parse('amount:$1,200')
    expect(result.amountMin).toBe(1200)
    expect(result.amountMax).toBe(1200)
  })

  it('ignores an unparseable amount value', () => {
    const result = parse('amount: abc')
    expect(result.amountMin).toBeUndefined()
    expect(result.amountMax).toBeUndefined()
  })

  it('leaves a bare number as free text for the backend to match', () => {
    expect(parse('12.34').text).toBe('12.34')
  })

  /**
   * The shared amount vocabulary. The backend has its own matcher for the
   * same strings (_AMOUNT_SEARCH_RE in repositories/transaction_repo.py) —
   * irreducible, since this one runs while the user types and that one runs
   * over SQL — so both suites carry these exact cases. A trailing dot is the
   * one that mattered: "12." is a half-typed amount, and rejecting it blanked
   * the results mid-keystroke, which reads as "typing a dot breaks search".
   */
  it.each([
    ['12', 12],
    ['12.', 12],
    ['12.34', 12.34],
    ['.34', 0.34],
    ['$1,200', 1200],
    ['$1,200.', 1200],
  ])('reads %s as the amount %s', (input, expected) => {
    const result = parse(`amount:${input}`)
    expect(result.amountMin).toBe(expected)
    expect(result.amountMax).toBe(expected)
  })

  it.each([['abc'], ['12.34.56'], ['']])('does not read %s as an amount', (input) => {
    const result = parse(`amount:${input}`)
    expect(result.amountMin).toBeUndefined()
    expect(result.amountMax).toBeUndefined()
  })
})

describe('date: filters (now = Tue 2026-08-11)', () => {
  it('parses a bare M/D as a single day in the current year', () => {
    const result = parse('date: 3/15')
    expect(result.startDate).toBe('2026-03-15')
    expect(result.endDate).toBe('2026-03-15')
  })

  it('parses M/D/YYYY', () => {
    const result = parse('date:3/15/2025')
    expect(result.startDate).toBe('2025-03-15')
    expect(result.endDate).toBe('2025-03-15')
  })

  it('parses a two-digit year', () => {
    expect(parse('date: 3/15/25').startDate).toBe('2025-03-15')
  })

  it('parses an ISO date', () => {
    const result = parse('date: 2025-03-15')
    expect(result.startDate).toBe('2025-03-15')
    expect(result.endDate).toBe('2025-03-15')
  })

  it('parses a slash range', () => {
    const result = parse('date: 3/1-3/15')
    expect(result.startDate).toBe('2026-03-01')
    expect(result.endDate).toBe('2026-03-15')
  })

  it('parses an ISO range with ..', () => {
    const result = parse('date: 2025-03-01..2025-03-15')
    expect(result.startDate).toBe('2025-03-01')
    expect(result.endDate).toBe('2025-03-15')
  })

  it('parses an open-ended lower bound', () => {
    const result = parse('date:>3/1')
    expect(result.startDate).toBe('2026-03-01')
    expect(result.endDate).toBeUndefined()
  })

  it('parses an open-ended upper bound', () => {
    const result = parse('date:<3/15')
    expect(result.endDate).toBe('2026-03-15')
    expect(result.startDate).toBeUndefined()
  })

  it('falls back to natural language values', () => {
    const result = parse('date: last month')
    expect(result.startDate).toBe('2026-07-01')
    expect(result.endDate).toBe('2026-07-31')
  })

  it('rejects an impossible date rather than rolling over', () => {
    const result = parse('date: 2/30')
    expect(result.startDate).toBeUndefined()
    expect(result.text).toBeUndefined()
  })
})

describe('category and payee filters', () => {
  it('matches category by name', () => {
    const catMap = new Map([['cat-1', 'Groceries'], ['cat-2', 'Dining']])
    const result = parseTransactionSearch('category: groc', catMap, EMPTY_MAP)
    expect(result.categoryIds).toContain('cat-1')
    expect(result.categoryIds).not.toContain('cat-2')
  })

  it('matches payee by name', () => {
    const payeeMap = new Map([['p-1', 'Starbucks'], ['p-2', 'Amazon']])
    const result = parseTransactionSearch('payee: star', EMPTY_MAP, payeeMap)
    expect(result.payeeIds).toContain('p-1')
    expect(result.payeeIds).not.toContain('p-2')
  })
})

describe('account filter', () => {
  const acctMap = new Map([['a-1', 'Checking'], ['a-2', 'Savings']])

  it('matches account by name when an account map is provided', () => {
    const result = parseTransactionSearch('account: check', EMPTY_MAP, EMPTY_MAP, acctMap)
    expect(result.accountIds).toEqual(['a-1'])
    expect(result.text).toBeUndefined()
  })

  it('parses compact account:name form', () => {
    const result = parseTransactionSearch('account:savings', EMPTY_MAP, EMPTY_MAP, acctMap)
    expect(result.accountIds).toEqual(['a-2'])
  })

  it('falls through to text without an account map (per-account register)', () => {
    const result = parseTransactionSearch('account:checking', EMPTY_MAP, EMPTY_MAP)
    expect(result.accountIds).toBeUndefined()
    expect(result.text).toBe('account:checking')
  })

  it('merges account ids across OR segments', () => {
    const result = parseTransactionSearch(
      'account: check OR account: sav', EMPTY_MAP, EMPTY_MAP, acctMap
    )
    expect(result.accountIds).toEqual(['a-1', 'a-2'])
    expect(result.isOrMode).toBe(true)
  })
})

// ─── OR keyword parsing ────────────────────────────────────────────────────────

describe('OR keyword', () => {
  it('sets isOrMode when OR keyword is present', () => {
    const result = parse('is: unapproved OR is: uncategorized')
    expect(result.isOrMode).toBe(true)
  })

  it('sets both unapproved and uncategorized when combined with OR', () => {
    const result = parse('is: unapproved OR is: uncategorized')
    expect(result.unapproved).toBe(true)
    expect(result.uncategorized).toBe(true)
  })

  it('does not set isOrMode without OR keyword', () => {
    const result = parse('is: unapproved is: uncategorized')
    expect(result.isOrMode).toBeUndefined()
  })

  it('OR is case-insensitive (lowercase)', () => {
    const result = parse('is: unapproved or is: uncategorized')
    expect(result.isOrMode).toBe(true)
  })

  it('OR is case-insensitive (mixed case)', () => {
    const result = parse('is: unapproved Or is: uncategorized')
    expect(result.isOrMode).toBe(true)
  })

  it('merges cleared from either side of OR', () => {
    const result = parse('is: cleared OR is: unapproved')
    expect(result.cleared).toBe('cleared')
    expect(result.unapproved).toBe(true)
    expect(result.isOrMode).toBe(true)
  })

  it('merges text parts from both OR segments', () => {
    const result = parse('foo OR bar')
    expect(result.text).toBe('foo bar')
    expect(result.isOrMode).toBe(true)
  })

  it('merges category IDs from both OR segments', () => {
    const catMap = new Map([['cat-1', 'Groceries'], ['cat-2', 'Dining']])
    const result = parseTransactionSearch('category: groc OR category: din', catMap, EMPTY_MAP)
    expect(result.categoryIds).toContain('cat-1')
    expect(result.categoryIds).toContain('cat-2')
    expect(result.isOrMode).toBe(true)
  })

  it('handles OR with only one meaningful side', () => {
    const result = parse('is: unapproved OR')
    expect(result.unapproved).toBe(true)
    expect(result.isOrMode).toBe(true)
  })

  it('single segment without OR has no isOrMode', () => {
    const result = parse('is: unapproved')
    expect(result.isOrMode).toBeUndefined()
  })

  it('empty query returns empty filters', () => {
    const result = parse('')
    expect(result).toEqual({})
  })

  it('amount filters merge with last segment winning', () => {
    const result = parse('amount:>10 OR amount:>50')
    expect(result.amountMin).toBe(50)
    expect(result.isOrMode).toBe(true)
  })
})

// ─── NOT keyword ──────────────────────────────────────────────────────────────

describe('NOT keyword', () => {
  it('parses NOT is: pending as excludeCleared', () => {
    expect(parse('NOT is: pending').excludeCleared).toBe('pending')
  })

  it('parses NOT is: cleared as excludeCleared', () => {
    expect(parse('NOT is: cleared').excludeCleared).toBe('cleared')
  })

  it('parses compact NOT is:pending', () => {
    expect(parse('NOT is:pending').excludeCleared).toBe('pending')
  })

  it('NOT is case-insensitive', () => {
    expect(parse('not is: pending').excludeCleared).toBe('pending')
  })

  it('NOT applies globally with OR segments', () => {
    const result = parse('is: unapproved OR is: uncategorized NOT is: pending')
    expect(result.unapproved).toBe(true)
    expect(result.uncategorized).toBe(true)
    expect(result.isOrMode).toBe(true)
    expect(result.excludeCleared).toBe('pending')
  })

  it('positive filters are preserved alongside NOT', () => {
    const result = parse('is: unapproved NOT is: pending')
    expect(result.unapproved).toBe(true)
    expect(result.excludeCleared).toBe('pending')
    expect(result.isOrMode).toBeUndefined()
  })

  it('does not set excludeCleared for unrecognised NOT target', () => {
    const result = parse('NOT foo')
    expect(result.excludeCleared).toBeUndefined()
    expect(result.text).toBe('NOT foo')
  })
})

// ─── hasActiveFilters ──────────────────────────────────────────────────────────

describe('hasActiveFilters', () => {
  it('returns false for empty filters', () => {
    expect(hasActiveFilters({})).toBe(false)
  })

  it('returns true when unapproved is set', () => {
    expect(hasActiveFilters({ unapproved: true })).toBe(true)
  })

  it('returns true when text is set', () => {
    expect(hasActiveFilters({ text: 'coffee' })).toBe(true)
  })

  it('returns true for OR-mode filters', () => {
    expect(hasActiveFilters({ unapproved: true, uncategorized: true, isOrMode: true })).toBe(true)
  })

  it('isOrMode alone does not count as active (no data filter)', () => {
    expect(hasActiveFilters({ isOrMode: true })).toBe(false)
  })

  it('returns true when excludeCleared is set', () => {
    expect(hasActiveFilters({ excludeCleared: 'pending' })).toBe(true)
  })

  it('returns true for date, direction, and transfer filters', () => {
    expect(hasActiveFilters({ startDate: '2026-08-01' })).toBe(true)
    expect(hasActiveFilters({ direction: 'inflow' })).toBe(true)
    expect(hasActiveFilters({ isTransfer: false })).toBe(true)
  })
})

// ─── Direction and transfer tokens ─────────────────────────────────────────────

describe('is: inflow / outflow / transfer', () => {
  it('parses is: inflow (spaced) and is:outflow (compact)', () => {
    expect(parse('is: inflow').direction).toBe('inflow')
    expect(parse('is:outflow').direction).toBe('outflow')
  })

  it('parses is: transfer and compact is:transfer', () => {
    expect(parse('is: transfer').isTransfer).toBe(true)
    expect(parse('is:transfer').isTransfer).toBe(true)
  })

  it('parses is: unpaired, spaced and compact', () => {
    // The hygiene panel links here. A transfer leg whose partner never
    // arrived is not expressible via is:transfer, which tests the partner
    // link alone — so this is its own token rather than a mode of that one.
    expect(parse('is: unpaired').unpairedTransfers).toBe(true)
    expect(parse('is:unpaired').unpairedTransfers).toBe(true)
  })

  it('keeps is: unpaired distinct from is: transfer', () => {
    expect(parse('is:unpaired').isTransfer).toBeUndefined()
    expect(parse('is:transfer').unpairedTransfers).toBeUndefined()
  })

  it('counts is: unpaired as an active filter', () => {
    // Without this the register would fetch a single unfiltered page and
    // present it as the whole answer.
    expect(hasActiveFilters({ unpairedTransfers: true })).toBe(true)
  })

  it('parses NOT is: transfer as exclusion (spaced and compact)', () => {
    expect(parse('NOT is: transfer').isTransfer).toBe(false)
    expect(parse('NOT is:transfer').isTransfer).toBe(false)
  })

  it('combines direction with other filters and text', () => {
    const f = parse('is:outflow coffee is: uncleared')
    expect(f.direction).toBe('outflow')
    expect(f.cleared).toBe('uncleared')
    expect(f.text).toBe('coffee')
  })

  it('survives OR merging', () => {
    const f = parse('is:inflow OR is: transfer')
    expect(f.direction).toBe('inflow')
    expect(f.isTransfer).toBe(true)
    expect(f.isOrMode).toBe(true)
  })
})

// ─── Natural-language date tokens ──────────────────────────────────────────────

describe('date tokens (now = Tue 2026-08-11)', () => {
  it('parses today', () => {
    const f = parse('today')
    expect(f.startDate).toBe('2026-08-11')
    expect(f.endDate).toBe('2026-08-11')
    expect(f.text).toBeUndefined()
  })

  it('parses yesterday', () => {
    const f = parse('yesterday')
    expect(f.startDate).toBe('2026-08-10')
    expect(f.endDate).toBe('2026-08-10')
  })

  it('parses this week as the current Monday–Sunday week', () => {
    const f = parse('this week')
    expect(f.startDate).toBe('2026-08-10')
    expect(f.endDate).toBe('2026-08-16')
  })

  it('parses last week as the previous Monday–Sunday week', () => {
    const f = parse('last week')
    expect(f.startDate).toBe('2026-08-03')
    expect(f.endDate).toBe('2026-08-09')
  })

  it('parses this month and last month as calendar months', () => {
    const thisMonth = parse('this month')
    expect(thisMonth.startDate).toBe('2026-08-01')
    expect(thisMonth.endDate).toBe('2026-08-31')
    const lastMonth = parse('last month')
    expect(lastMonth.startDate).toBe('2026-07-01')
    expect(lastMonth.endDate).toBe('2026-07-31')
  })

  it('parses this year and last year as calendar years', () => {
    const thisYear = parse('this year')
    expect(thisYear.startDate).toBe('2026-01-01')
    expect(thisYear.endDate).toBe('2026-12-31')
    const lastYear = parse('last year')
    expect(lastYear.startDate).toBe('2025-01-01')
    expect(lastYear.endDate).toBe('2025-12-31')
  })

  it('parses a past month name in the current year', () => {
    const f = parse('march')
    expect(f.startDate).toBe('2026-03-01')
    expect(f.endDate).toBe('2026-03-31')
  })

  it('resolves a month after the current one to last year', () => {
    const f = parse('september')
    expect(f.startDate).toBe('2025-09-01')
    expect(f.endDate).toBe('2025-09-30')
  })

  it('accepts an explicit trailing year', () => {
    const f = parse('march 2025')
    expect(f.startDate).toBe('2025-03-01')
    expect(f.endDate).toBe('2025-03-31')
    expect(f.text).toBeUndefined()
  })

  it('accepts three-letter month abbreviations', () => {
    const f = parse('feb')
    expect(f.startDate).toBe('2026-02-01')
    expect(f.endDate).toBe('2026-02-28')
  })

  it('parses a month range like jan-mar', () => {
    const f = parse('jan-mar')
    expect(f.startDate).toBe('2026-01-01')
    expect(f.endDate).toBe('2026-03-31')
  })

  it('wraps a range crossing the year boundary (nov-feb)', () => {
    const f = parse('nov-feb')
    expect(f.startDate).toBe('2025-11-01')
    expect(f.endDate).toBe('2026-02-28')
  })

  it('combines dates with other filters and text', () => {
    const f = parse('last month is:outflow coffee')
    expect(f.startDate).toBe('2026-07-01')
    expect(f.endDate).toBe('2026-07-31')
    expect(f.direction).toBe('outflow')
    expect(f.text).toBe('coffee')
  })

  it('leaves "this" and "last" as text without a period word', () => {
    const f = parse('last chance')
    expect(f.startDate).toBeUndefined()
    expect(f.text).toBe('last chance')
  })

  it('leaves quoted month names as text', () => {
    const f = parse('"march"')
    expect(f.startDate).toBeUndefined()
    expect(f.text).toBe('"march"')
  })
})

// ─── Filter chips ──────────────────────────────────────────────────────────────

describe('describeSearchChips', () => {
  // A chip now exists exactly when a filter does, so these need the same maps
  // the parser gets — that is the whole point of the change.
  const CATS = new Map([['cat-1', 'Groceries']])
  const PAYEES = new Map([['p-1', 'Starbucks']])
  const ACCOUNTS = new Map([['a-1', 'Checking'], ['a-2', 'Savings']])

  function chips(query: string, accounts: Map<string, string> = EMPTY_MAP) {
    return describeSearchChips(query, CATS, PAYEES, accounts, NOW)
  }

  it('returns no chips for plain text', () => {
    expect(chips('coffee shop')).toEqual([])
  })

  it('describes is:/has: filters with labels', () => {
    const labels = chips('is: cleared has:attachment is:transfer').map((c) => c.label)
    expect(labels).toEqual(['Cleared', 'Has attachment', 'Transfer'])
  })

  it('describes NOT filters', () => {
    const labels = chips('NOT is: pending NOT has:attachment').map((c) => c.label)
    expect(labels).toEqual(['Not pending', 'No attachment'])
  })

  it('describes category, payee, and amount filters', () => {
    const labels = chips('category: groc payee:starbucks amount:>100').map((c) => c.label)
    expect(labels).toEqual(['Category: groc', 'Payee: starbucks', 'Amount: >100'])
  })

  it('describes account filters only with an account map', () => {
    expect(chips('account:checking').map((c) => c.label)).toEqual([])
    expect(chips('account:checking', ACCOUNTS).map((c) => c.label)).toEqual(['Account: checking'])
  })

  it('describes date tokens with friendly labels', () => {
    const labels = chips('today last week march 2025 jan-mar').map((c) => c.label)
    expect(labels).toEqual(['Today', 'Last week', 'March 2025', 'Jan–Mar'])
  })

  it('free text between filters produces no chip', () => {
    const labels = chips('is: cleared coffee last month').map((c) => c.label)
    expect(labels).toEqual(['Cleared', 'Last month'])
  })
})

describe('a chip exists exactly when a filter does', () => {
  // The chips were a second walk over the tokens with their own copy of every
  // recognizer, and they disagreed with the parser. Each case below drew a
  // chip for a filter that was not applied, or hid a token that was silently
  // dropped. The pairing is the invariant: same query, both answers.
  const CATS = new Map([['cat-1', 'Groceries']])
  const PAYEES = new Map([['p-1', 'Starbucks']])

  const both = (query: string, accounts = EMPTY_MAP) => ({
    filters: parseTransactionSearch(query, CATS, PAYEES, accounts, NOW),
    labels: describeSearchChips(query, CATS, PAYEES, accounts, NOW).map((c) => c.label),
  })

  it('a category that matches nothing draws no chip', () => {
    const { filters, labels } = both('category: zzz')
    expect(filters.categoryIds).toBeUndefined()
    expect(labels).toEqual([])
  })

  it('a category that matches does draw one', () => {
    const { filters, labels } = both('category: groc')
    expect(filters.categoryIds).toEqual(['cat-1'])
    expect(labels).toEqual(['Category: groc'])
  })

  it('a payee that matches nothing draws no chip', () => {
    const { filters, labels } = both('payee: nobody')
    expect(filters.payeeIds).toBeUndefined()
    expect(labels).toEqual([])
  })

  it('an unreadable amount draws no chip', () => {
    const { filters, labels } = both('amount: abc')
    expect(filters.amountMin).toBeUndefined()
    expect(filters.amountMax).toBeUndefined()
    expect(labels).toEqual([])
  })

  it('an unrecognised is: value is searched as text rather than swallowed', () => {
    // It used to vanish: no filter, no chip, and the token dropped, so the
    // register quietly ignored what the user typed.
    const { filters, labels } = both('is:bogus')
    expect(labels).toEqual([])
    expect(filters.text).toBe('is:bogus')
  })

  it('an unrecognised NOT is a text search, and says so by drawing no chip', () => {
    const { filters, labels } = both('NOT is:uncategorized')
    expect(labels).toEqual([])
    expect(filters.text).toBe('NOT is:uncategorized')
  })

  it('an account filter off the all-accounts register draws no chip', () => {
    const { filters, labels } = both('account:checking')
    expect(filters.accountIds).toBeUndefined()
    expect(labels).toEqual([])
  })

  it('chips survive an OR split with the right token indices', () => {
    const query = 'is: cleared OR is: pending'
    const chips = describeSearchChips(query, CATS, PAYEES, EMPTY_MAP, NOW)
    expect(chips.map((c) => c.label)).toEqual(['Cleared', 'Pending'])
    expect(removeSearchChip(query, chips[0])).toBe('is: pending')
  })

  it('chips survive a NOT that precedes other filters', () => {
    const query = 'NOT is: pending category: groc'
    const chips = describeSearchChips(query, CATS, PAYEES, EMPTY_MAP, NOW)
    expect(chips.map((c) => c.label)).toEqual(['Not pending', 'Category: groc'])
    expect(removeSearchChip(query, chips[1])).toBe('NOT is: pending')
  })
})

describe('removeSearchChip', () => {
  const CATS = new Map([['cat-1', 'Groceries']])
  const PAYEES = new Map([['p-1', 'Starbucks']])

  function removeByLabel(query: string, label: string, accounts: Map<string, string> = EMPTY_MAP) {
    const chip = describeSearchChips(query, CATS, PAYEES, accounts, NOW).find(
      (c) => c.label === label
    )
    expect(chip).toBeDefined()
    return removeSearchChip(query, chip!)
  }

  it('removes a spaced filter and keeps the rest', () => {
    expect(removeByLabel('is: cleared coffee march', 'Cleared')).toBe('coffee march')
  })

  it('removes a multi-token date filter', () => {
    expect(removeByLabel('last week is:outflow', 'Last week')).toBe('is:outflow')
  })

  it('removes a month + year pair together', () => {
    expect(removeByLabel('march 2025 coffee', 'March 2025')).toBe('coffee')
  })

  it('drops an OR left dangling at the edge', () => {
    expect(removeByLabel('is:cleared OR is:pending', 'Cleared')).toBe('is:pending')
    expect(removeByLabel('is:cleared OR is:pending', 'Pending')).toBe('is:cleared')
  })

  it('removes NOT filters including the NOT token', () => {
    expect(removeByLabel('coffee NOT is: pending', 'Not pending')).toBe('coffee')
  })

  it('removing the only chip empties the query', () => {
    expect(removeByLabel('is:transfer', 'Transfer')).toBe('')
  })
})

describe('chip provenance round-trips', () => {
  // The chips carry token indices through a NOT extraction and an OR split.
  // If an index is off by one, removeSearchChip deletes the wrong token —
  // silently, producing a query that still parses. These walk every chip of
  // every shape and assert the removal is exact.
  const CATS = new Map([['cat-1', 'Groceries']])
  const PAYEES = new Map([['p-1', 'Starbucks']])
  const ACCTS = new Map([['a-1', 'Checking']])

  const QUERIES = [
    'is: cleared',
    'is:cleared',
    'has:attachment coffee',
    'NOT is: pending',
    'NOT is:pending category: groc',
    'category: groc payee:star',
    'category:groc OR payee:star',
    'is: cleared OR is: pending OR is:reconciled',
    'account:checking amount:>100',
    'today category: groc',
    'last month is:unapproved coffee',
    'NOT has:attachment OR is:transfer',
    'amount:10-20 payee: star march 2025',
  ]

  for (const query of QUERIES) {
    it(`every chip in "${query}" removes exactly its own tokens`, () => {
      const chips = describeSearchChips(query, CATS, PAYEES, ACCTS, NOW)
      expect(chips.length).toBeGreaterThan(0)

      for (const chip of chips) {
        const after = removeSearchChip(query, chip)
        // The removed chip is gone...
        const remaining = describeSearchChips(after, CATS, PAYEES, ACCTS, NOW)
        expect(remaining.map((c) => c.label)).not.toContain(chip.label)
        // ...and every other chip survives.
        const others = chips.filter((c) => c.key !== chip.key).map((c) => c.label)
        for (const label of others) expect(remaining.map((c) => c.label)).toContain(label)
      }
    })
  }

  it('removing every chip leaves only free text', () => {
    const query = 'is: cleared coffee category: groc NOT is:pending'
    let current = query
    for (;;) {
      const chips = describeSearchChips(current, CATS, PAYEES, ACCTS, NOW)
      if (chips.length === 0) break
      current = removeSearchChip(current, chips[0])
    }
    expect(current.trim()).toBe('coffee')
    expect(parseTransactionSearch(current, CATS, PAYEES, ACCTS, NOW).text).toBe('coffee')
  })
})
