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
 * The one place a match pattern is turned into a RegExp: case-insensitive,
 * unanchored, the way the backend applies it. Returns null for a pattern
 * that does not compile.
 */
export function compilePattern(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern, 'i')
  } catch {
    return null
  }
}

/** Test a pattern the way the backend will apply it. Null for an invalid pattern. */
export function testPattern(pattern: string, name: string): boolean | null {
  const re = compilePattern(pattern)
  return re ? re.test(name) : null
}

/** Where a pattern first matches inside a name, so a preview can show the
 *  part it captured. Null when the pattern is invalid or does not match. */
export function matchSpan(pattern: string, name: string): { start: number; end: number } | null {
  const re = compilePattern(pattern)
  if (!re) return null
  const m = re.exec(name)
  return m ? { start: m.index, end: m.index + m[0].length } : null
}

export interface ClaimablePayee {
  name: string
  mapping_samples?: string[] | null
}

/**
 * The other payees a pattern would also claim — by name or by any of their
 * recorded bank-name samples. On import the longest matching pattern wins,
 * so a general pattern that claims a neighbour is a real cost, not a
 * curiosity; this is what lets a preview say so.
 */
export function claimedNames(pattern: string, others: ClaimablePayee[]): string[] {
  const re = compilePattern(pattern)
  if (!re) return []
  return others
    .filter((p) => re.test(p.name) || (p.mapping_samples ?? []).some((s) => re.test(s)))
    .map((p) => p.name)
}

/** Split a pattern on top-level `|` (ignoring alternation inside groups,
 * character classes, and escapes). */
function splitTopLevelAlternation(pattern: string): string[] {
  const parts: string[] = []
  let depth = 0
  let inClass = false
  let current = ''
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i]
    if (c === '\\') {
      current += c + (pattern[i + 1] ?? '')
      i++
      continue
    }
    if (inClass) {
      current += c
      if (c === ']') inClass = false
      continue
    }
    if (c === '[') inClass = true
    else if (c === '(') depth++
    else if (c === ')') depth--
    else if (c === '|' && depth === 0) {
      parts.push(current)
      current = ''
      continue
    }
    current += c
  }
  parts.push(current)
  return parts
}

/** Unwrap `(?:...)` when the whole string is one non-capturing group. */
function stripNonCaptureWrap(pattern: string): string {
  if (!pattern.startsWith('(?:') || !pattern.endsWith(')')) return pattern
  let depth = 0
  let inClass = false
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i]
    if (c === '\\') {
      i++
      continue
    }
    if (inClass) {
      if (c === ']') inClass = false
      continue
    }
    if (c === '[') inClass = true
    else if (c === '(') depth++
    else if (c === ')') {
      depth--
      // The opening group closes before the end: the wrap isn't whole-string
      if (depth === 0 && i < pattern.length - 1) return pattern
    }
  }
  return pattern.slice(3, -1)
}

/**
 * Union two or more patterns into one that matches what any of them matched:
 * `(?:a)|(?:b)`. Existing top-level alternations are flattened and duplicate
 * branches dropped, so repeatedly extending a pattern never nests. Returns
 * null when any input (or the result) is not a valid regex.
 */
export function unionPatterns(...patterns: string[]): string | null {
  const branches: string[] = []
  const seen = new Set<string>()
  for (const raw of patterns) {
    const pattern = raw.trim()
    if (!pattern) continue
    if (testPattern(pattern, '') === null) return null
    for (const part of splitTopLevelAlternation(pattern)) {
      const bare = stripNonCaptureWrap(part.trim())
      if (bare && !seen.has(bare)) {
        seen.add(bare)
        branches.push(bare)
      }
    }
  }
  if (branches.length === 0) return null
  const union = branches.length === 1 ? branches[0] : branches.map((b) => `(?:${b})`).join('|')
  return testPattern(union, '') === null ? null : union
}
