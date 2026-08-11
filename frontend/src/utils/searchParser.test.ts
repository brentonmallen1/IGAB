import { describe, it, expect } from 'vitest'
import { parseTransactionSearch, hasActiveFilters } from './searchParser'

const EMPTY_MAP = new Map<string, string>()

function parse(query: string) {
  return parseTransactionSearch(query, EMPTY_MAP, EMPTY_MAP)
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
})
