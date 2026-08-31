import { describe, it, expect } from 'vitest'
import {
  claimedNames,
  escapeRegex,
  matchSpan,
  suggestPayeeRegex,
  testPattern,
  unionPatterns,
} from './payeeRegex'

describe('suggestPayeeRegex', () => {
  it('generalizes a shared prefix with random suffixes', () => {
    const names = ['ACH DEPOSIT PAYROLL 8842', 'ACH DEPOSIT PAYROLL 9921']
    const pattern = suggestPayeeRegex(names)
    expect(pattern).toBe('^ACH DEPOSIT PAYROLL ')
    for (const n of names) expect(testPattern(pattern!, n)).toBe(true)
    expect(testPattern(pattern!, 'ACH DEPOSIT PAYROLL 1234-XK')).toBe(true)
    expect(testPattern(pattern!, 'ACH WITHDRAWAL 8842')).toBe(false)
  })

  it('does not cut mid-token on the prefix', () => {
    // Char-wise common prefix is "CHE" — worthless and overmatching.
    expect(suggestPayeeRegex(['CHEVRON 001', 'CHECKERS 99'])).toBeNull()
  })

  it('keeps a full shared token when divergence starts at a boundary', () => {
    const pattern = suggestPayeeRegex(['AMZN Mktp US*1A2B3C', 'AMZN Mktp US*9Z8Y7X'])
    expect(pattern).toBe('^AMZN Mktp US\\*')
    expect(testPattern(pattern!, 'amzn mktp us*NEW123')).toBe(true)
  })

  it('uses prefix and suffix around a varying middle', () => {
    const names = ['POS DEBIT 4412 GROCERY OUTLET', 'POS DEBIT 991 GROCERY OUTLET']
    const pattern = suggestPayeeRegex(names)
    expect(pattern).toBe('^POS DEBIT .* GROCERY OUTLET$')
    for (const n of names) expect(testPattern(pattern!, n)).toBe(true)
    expect(testPattern(pattern!, 'POS DEBIT 123 HARDWARE STORE')).toBe(false)
  })

  it('handles suffix-only structure', () => {
    const names = ['1099 TRANSFER TO SAVINGS', 'A-42 TRANSFER TO SAVINGS']
    const pattern = suggestPayeeRegex(names)
    expect(pattern).toBe(' TRANSFER TO SAVINGS$')
    for (const n of names) expect(testPattern(pattern!, n)).toBe(true)
  })

  it('is case-insensitive when finding shared structure', () => {
    const pattern = suggestPayeeRegex(['Paypal *Spotify', 'PAYPAL *STEAM'])
    expect(pattern).toBe('^Paypal \\*')
  })

  it('returns an exact pattern when all names are identical', () => {
    expect(suggestPayeeRegex(['Costco', 'costco', 'COSTCO'])).toBe('^Costco$')
  })

  it('returns null when there is nothing meaningful in common', () => {
    expect(suggestPayeeRegex(['Trader Joes', 'Shell Oil'])).toBeNull()
  })

  it('returns null for fewer than two distinct names', () => {
    expect(suggestPayeeRegex([])).toBeNull()
    expect(suggestPayeeRegex(['Costco'])).toBeNull()
    expect(suggestPayeeRegex(['Costco', '  ', ''])).toBeNull()
  })

  it('escapes regex metacharacters from names', () => {
    const pattern = suggestPayeeRegex(['SQ *COFFEE (DOWNTOWN) 12', 'SQ *COFFEE (DOWNTOWN) 99'])
    expect(pattern).toBe('^SQ \\*COFFEE \\(DOWNTOWN\\) ')
    expect(testPattern(pattern!, 'SQ *COFFEE (DOWNTOWN) 4471')).toBe(true)
    expect(testPattern(pattern!, 'SQ XCOFFEE DOWNTOWN 12')).toBe(false)
  })

  it('never suggests a pattern that misses one of its own inputs', () => {
    const cases = [
      ['VENMO PAYMENT 100221', 'VENMO PAYMENT 88123', 'VENMO PAYMENT XK-1'],
      ['Uber Trip 4412', 'Uber Trip HELP.UBER.COM'],
      ['ATM WITHDRAWAL #100', 'ATM WITHDRAWAL #92'],
      ['Netflix.com', 'NETFLIX.COM 866-579-7172'],
    ]
    for (const names of cases) {
      const pattern = suggestPayeeRegex(names)
      if (pattern === null) continue
      for (const n of names) {
        expect(testPattern(pattern, n), `${pattern} should match ${n}`).toBe(true)
      }
    }
  })
})

describe('testPattern', () => {
  it('matches case-insensitively and unanchored, like the backend', () => {
    expect(testPattern('payroll', 'ACH DEPOSIT PAYROLL 123')).toBe(true)
  })

  it('returns null for invalid patterns', () => {
    expect(testPattern('([bad', 'anything')).toBeNull()
  })
})

describe('matchSpan', () => {
  it('finds the first match case-insensitively', () => {
    expect(matchSpan('payroll', 'ACH DEPOSIT PAYROLL 123')).toEqual({ start: 12, end: 19 })
  })

  it('honours anchors', () => {
    expect(matchSpan('^ACH DEPOSIT PAYROLL ', 'ACH DEPOSIT PAYROLL 123')).toEqual({
      start: 0,
      end: 20,
    })
    expect(matchSpan('^PAYROLL', 'ACH DEPOSIT PAYROLL 123')).toBeNull()
  })

  it('is null for a miss or an invalid pattern', () => {
    expect(matchSpan('RENT', 'ACH DEPOSIT PAYROLL 123')).toBeNull()
    expect(matchSpan('([bad', 'anything')).toBeNull()
  })
})

describe('claimedNames', () => {
  const others = [
    { name: 'ACH WITHDRAWAL 12', mapping_samples: [] },
    { name: 'Rent', mapping_samples: ['ACH DEPOSIT RENT REFUND'] },
    { name: 'Netflix', mapping_samples: null },
  ]

  it('names payees claimed by name or by a sample', () => {
    expect(claimedNames('^ACH', others)).toEqual(['ACH WITHDRAWAL 12', 'Rent'])
    expect(claimedNames('^ACH DEPOSIT PAYROLL ', others)).toEqual([])
  })

  it('claims nothing for an invalid pattern', () => {
    expect(claimedNames('([bad', others)).toEqual([])
  })
})

describe('escapeRegex', () => {
  it('escapes all metacharacters', () => {
    const raw = 'a.b*c+d?e^f$g{h}i(j)k|l[m]n\\o'
    expect(new RegExp(`^${escapeRegex(raw)}$`).test(raw)).toBe(true)
  })
})

describe('unionPatterns', () => {
  it('unions two plain patterns and matches what each matched', () => {
    const union = unionPatterns('^ACH PAYROLL', 'DIRECT DEP$')
    expect(union).toBe('(?:^ACH PAYROLL)|(?:DIRECT DEP$)')
    expect(testPattern(union!, 'ACH PAYROLL 123')).toBe(true)
    expect(testPattern(union!, 'ACME DIRECT DEP')).toBe(true)
    expect(testPattern(union!, 'SOMETHING ELSE')).toBe(false)
  })

  it('flattens an already-unioned pattern instead of nesting', () => {
    const first = unionPatterns('^A', '^B')!
    const second = unionPatterns(first, '^C')
    expect(second).toBe('(?:^A)|(?:^B)|(?:^C)')
  })

  it('drops duplicate branches', () => {
    expect(unionPatterns('^A', '^A')).toBe('^A')
    expect(unionPatterns('(?:^A)|(?:^B)', '^B')).toBe('(?:^A)|(?:^B)')
  })

  it('does not split alternation inside groups or classes', () => {
    const union = unionPatterns('^(A|B) CORP', '[|]END$')
    expect(union).toBe('(?:^(A|B) CORP)|(?:[|]END$)')
    expect(testPattern(union!, 'A CORP')).toBe(true)
    expect(testPattern(union!, 'X |END')).toBe(true)
  })

  it('keeps a non-capture wrap that is not the whole branch', () => {
    // "(?:A)(?:B)" must not be unwrapped into "A)(?:B"
    const union = unionPatterns('(?:A)(?:B)', '^C')
    expect(union).toBe('(?:(?:A)(?:B))|(?:^C)')
    expect(testPattern(union!, 'AB')).toBe(true)
  })

  it('returns the single branch when only one pattern is given', () => {
    expect(unionPatterns('^ONLY')).toBe('^ONLY')
    expect(unionPatterns('^ONLY', '', '  ')).toBe('^ONLY')
  })

  it('returns null when an input pattern is invalid or empty', () => {
    expect(unionPatterns('([bad', '^ok')).toBeNull()
    expect(unionPatterns('', '  ')).toBeNull()
  })
})
