/**
 * Suggest a regex match pattern that generalizes a set of payee names.
 *
 * Used by the merge modal: when merging e.g. "ACH DEPOSIT PAYROLL 8842" and
 * "ACH DEPOSIT PAYROLL 9921", the shared structure becomes a pattern
 * (`^ACH DEPOSIT PAYROLL `) that future imports with fresh random suffixes
 * will still hit. Generated patterns only use escaped literals, `.*`, `^`
 * and `$`, so they behave identically in JS (preview) and Python (matching).
 */

const isWordChar = (c: string) => /[a-z0-9]/i.test(c)

export function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Trim a trailing partial token (we cut mid-word if the boundary char on both
 * sides is alphanumeric — `^CHE` from CHEVRON/CHECKERS overmatches). */
function trimPartialTokenEnd(prefix: string, names: string[], p: number): string {
  const cutMidToken =
    p > 0 && isWordChar(prefix[p - 1]) && names.some((n) => n.length > p && isWordChar(n[p]))
  if (!cutMidToken) return prefix
  let i = prefix.length
  while (i > 0 && isWordChar(prefix[i - 1])) i--
  return prefix.slice(0, i)
}

function trimPartialTokenStart(suffix: string, names: string[], s: number): string {
  const cutMidToken =
    s > 0 &&
    isWordChar(suffix[0]) &&
    names.some((n) => n.length > s && isWordChar(n[n.length - s - 1]))
  if (!cutMidToken) return suffix
  let i = 0
  while (i < suffix.length && isWordChar(suffix[i])) i++
  return suffix.slice(i)
}

export function suggestPayeeRegex(rawNames: string[]): string | null {
  const names = [...new Set(rawNames.map((n) => n.trim()).filter(Boolean))]
  if (names.length < 2) return null

  const lower = names.map((n) => n.toLowerCase())
  const minLen = Math.min(...lower.map((n) => n.length))

  let p = 0
  while (p < minLen && lower.every((n) => n[p] === lower[0][p])) p++

  // All names identical (case-insensitively): exact-match pattern.
  if (lower.every((n) => n.length === p)) {
    return `^${escapeRegex(names[0])}$`
  }

  let s = 0
  while (
    s < minLen - p &&
    lower.every((n) => n[n.length - 1 - s] === lower[0][lower[0].length - 1 - s])
  ) {
    s++
  }

  const prefix = trimPartialTokenEnd(names[0].slice(0, p), names, p)
  const suffix = trimPartialTokenStart(names[0].slice(names[0].length - s), names, s)

  // Require enough shared substance for the pattern to mean something.
  const substance = (prefix + suffix).replace(/[^a-z0-9]/gi, '').length
  if (substance < 3) return null

  if (prefix && suffix) return `^${escapeRegex(prefix)}.*${escapeRegex(suffix)}$`
  if (prefix) return `^${escapeRegex(prefix)}`
  return `${escapeRegex(suffix)}$`
}

/**
 * Test a pattern the way the backend will apply it: case-insensitive,
 * unanchored search. Returns null for an invalid pattern.
 */
export function testPattern(pattern: string, name: string): boolean | null {
  try {
    return new RegExp(pattern, 'i').test(name)
  } catch {
    return null
  }
}
