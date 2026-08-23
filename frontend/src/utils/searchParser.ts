export interface TransactionFilters {
  text?: string
  cleared?: string
  excludeCleared?: string
  uncategorized?: boolean
  unapproved?: boolean
  categoryIds?: string[]
  payeeIds?: string[]
  /** Only resolved when an account map is supplied (all-accounts register) */
  accountIds?: string[]
  amountMin?: number | null
  amountMax?: number | null
  /** true = only rows with an image attached; false = only rows without */
  hasAttachment?: boolean
  /** ISO yyyy-mm-dd bounds resolved from natural-language date tokens */
  startDate?: string
  endDate?: string
  direction?: 'inflow' | 'outflow'
  /** true = only transfers; false = exclude transfers */
  isTransfer?: boolean
  /** Transfer legs whose partner never arrived. Deliberately separate from
   *  `isTransfer`, which tests the partner link alone and so cannot express
   *  "names a transfer payee but has no partner". This is what the account
   *  hygiene panel links to. */
  unpairedTransfers?: boolean
  isOrMode?: boolean
}

export function hasActiveFilters(f: TransactionFilters): boolean {
  return !!(
    f.text ||
    f.cleared ||
    f.excludeCleared ||
    f.uncategorized ||
    f.unapproved ||
    f.unpairedTransfers ||
    (f.categoryIds?.length ?? 0) > 0 ||
    (f.payeeIds?.length ?? 0) > 0 ||
    (f.accountIds?.length ?? 0) > 0 ||
    f.amountMin != null ||
    f.amountMax != null ||
    f.hasAttachment != null ||
    f.startDate != null ||
    f.endDate != null ||
    f.direction != null ||
    f.isTransfer != null
  )
}

const ATTACHMENT_VALUES = new Set(['attachment', 'image', 'receipt'])

const CLEARED_VALUES = new Set(['cleared', 'uncleared', 'pending', 'reconciled'])

const DIRECTION_VALUES = new Set(['inflow', 'outflow'])

// prettier-ignore
const MONTH_NAMES: Record<string, number> = {
  jan: 0, january: 0, feb: 1, february: 1, mar: 2, march: 2, apr: 3, april: 3,
  may: 4, jun: 5, june: 5, jul: 6, july: 6, aug: 7, august: 7,
  sep: 8, sept: 8, september: 8, oct: 9, october: 9, nov: 10, november: 10,
  dec: 11, december: 11,
}

const PERIOD_WORDS = new Set(['week', 'month', 'year'])

function toIsoDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** Monday of the week containing d. */
function startOfWeek(d: Date): Date {
  const dow = (d.getDay() + 6) % 7
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - dow)
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

interface DateTokenMatch {
  startDate: string
  endDate: string
  label: string
  /** number of tokens consumed, starting at index i */
  consumed: number
}

/**
 * Recognise natural-language date tokens at position i:
 * today · yesterday · this/last week|month|year · month names (optionally
 * followed by a 4-digit year) · month ranges like "jan-mar". Bare month
 * names resolve to the most recent occurrence (a month after the current
 * one means last year). Weeks run Monday–Sunday.
 */
function matchDateTokens(tokens: string[], i: number, now: Date): DateTokenMatch | null {
  const lower = tokens[i].toLowerCase()

  if (lower === 'today') {
    const d = toIsoDate(now)
    return { startDate: d, endDate: d, label: 'Today', consumed: 1 }
  }
  if (lower === 'yesterday') {
    const y = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
    const d = toIsoDate(y)
    return { startDate: d, endDate: d, label: 'Yesterday', consumed: 1 }
  }

  if (lower === 'this' || lower === 'last') {
    const period = tokens[i + 1]?.toLowerCase()
    if (!period || !PERIOD_WORDS.has(period)) return null
    const label = `${capitalize(lower)} ${period}`
    if (period === 'week') {
      const monday = startOfWeek(now)
      if (lower === 'last') monday.setDate(monday.getDate() - 7)
      const sunday = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6)
      return { startDate: toIsoDate(monday), endDate: toIsoDate(sunday), label, consumed: 2 }
    }
    if (period === 'month') {
      const m = lower === 'last' ? now.getMonth() - 1 : now.getMonth()
      const start = new Date(now.getFullYear(), m, 1)
      const end = new Date(now.getFullYear(), m + 1, 0)
      return { startDate: toIsoDate(start), endDate: toIsoDate(end), label, consumed: 2 }
    }
    const year = lower === 'last' ? now.getFullYear() - 1 : now.getFullYear()
    return {
      startDate: `${year}-01-01`,
      endDate: `${year}-12-31`,
      label,
      consumed: 2,
    }
  }

  // Month range: jan-mar. The end month picks the most recent past
  // occurrence; a start month "after" the end month wraps into the prior
  // year (nov-feb).
  const rangeMatch = lower.match(/^([a-z]+)-([a-z]+)$/)
  if (rangeMatch && rangeMatch[1] in MONTH_NAMES && rangeMatch[2] in MONTH_NAMES) {
    const startMonth = MONTH_NAMES[rangeMatch[1]]
    const endMonth = MONTH_NAMES[rangeMatch[2]]
    const endYear = endMonth > now.getMonth() ? now.getFullYear() - 1 : now.getFullYear()
    const startYear = startMonth > endMonth ? endYear - 1 : endYear
    return {
      startDate: toIsoDate(new Date(startYear, startMonth, 1)),
      endDate: toIsoDate(new Date(endYear, endMonth + 1, 0)),
      label: `${capitalize(rangeMatch[1])}–${capitalize(rangeMatch[2])}`,
      consumed: 1,
    }
  }

  if (lower in MONTH_NAMES) {
    const month = MONTH_NAMES[lower]
    const yearToken = tokens[i + 1]?.match(/^\d{4}$/) ? Number(tokens[i + 1]) : null
    const year =
      yearToken ?? (month > now.getMonth() ? now.getFullYear() - 1 : now.getFullYear())
    return {
      startDate: toIsoDate(new Date(year, month, 1)),
      endDate: toIsoDate(new Date(year, month + 1, 0)),
      label: yearToken ? `${capitalize(lower)} ${yearToken}` : capitalize(lower),
      consumed: yearToken ? 2 : 1,
    }
  }

  return null
}

function validDate(y: number, m: number, d: number): Date | null {
  const dt = new Date(y, m, d)
  return dt.getFullYear() === y && dt.getMonth() === m && dt.getDate() === d ? dt : null
}

/** M/D · M/D/YY · M/D/YYYY · YYYY-MM-DD. Bare M/D assumes the current year. */
function parseExplicitDay(s: string, now: Date): Date | null {
  const iso = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (iso) return validDate(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]))

  const us = s.match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2}|\d{4}))?$/)
  if (us) {
    const year = us[3] ? (us[3].length === 2 ? 2000 + Number(us[3]) : Number(us[3])) : now.getFullYear()
    return validDate(year, Number(us[1]) - 1, Number(us[2]))
  }
  return null
}

function formatDay(d: Date): string {
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`
}

interface DateExprMatch {
  startDate?: string
  endDate?: string
  label: string
}

/**
 * The value side of a date: token — a single day, an open-ended bound
 * (>3/1, <3/15) or a range (3/1-3/15, 2025-03-01..2025-03-15). Natural
 * language values fall through to matchDateTokens.
 */
function matchExplicitDateExpr(expr: string, now: Date): DateExprMatch | null {
  const raw = expr.replace(/^"|"$/g, '')

  if (raw.startsWith('>')) {
    const d = parseExplicitDay(raw.replace(/^>=?/, ''), now)
    return d ? { startDate: toIsoDate(d), label: `On or after ${formatDay(d)}` } : null
  }
  if (raw.startsWith('<')) {
    const d = parseExplicitDay(raw.replace(/^<=?/, ''), now)
    return d ? { endDate: toIsoDate(d), label: `On or before ${formatDay(d)}` } : null
  }

  // Ranges: '..' separates any two forms; a bare '-' only when both sides
  // are slash dates, so ISO dates (which contain dashes) stay intact.
  let parts: string[] | null = null
  if (raw.includes('..')) parts = raw.split('..')
  else {
    const slashRange = raw.match(
      /^(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)-(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)$/
    )
    if (slashRange) parts = [slashRange[1], slashRange[2]]
  }
  if (parts) {
    if (parts.length !== 2) return null
    const a = parseExplicitDay(parts[0], now)
    const b = parseExplicitDay(parts[1], now)
    if (!a || !b) return null
    return { startDate: toIsoDate(a), endDate: toIsoDate(b), label: `${formatDay(a)} – ${formatDay(b)}` }
  }

  const day = parseExplicitDay(raw, now)
  return day ? { startDate: toIsoDate(day), endDate: toIsoDate(day), label: formatDay(day) } : null
}

/**
 * A date: token at position i, in either the compact (date:3/15) or spaced
 * (date: 3/15) form. Explicit forms win; anything else is handed to the
 * natural-language matcher so date: last month works too.
 */
function matchDateFilterToken(
  tokens: string[],
  i: number,
  now: Date
): (DateExprMatch & { consumed: number }) | null {
  const lower = tokens[i].toLowerCase()
  const compact = lower.match(/^date:(.+)$/)?.[1]

  if (compact !== undefined) {
    const explicit = matchExplicitDateExpr(compact, now)
    if (explicit) return { ...explicit, consumed: 1 }
    const natural = matchDateTokens([compact], 0, now)
    return natural ? { ...natural, consumed: 1 } : null
  }

  if (lower !== 'date:') return null

  const next = tokens[i + 1]
  if (!next) return null
  const explicit = matchExplicitDateExpr(next, now)
  if (explicit) return { ...explicit, consumed: 2 }
  const natural = matchDateTokens(tokens, i + 1, now)
  return natural ? { ...natural, consumed: natural.consumed + 1 } : null
}

function applyIsValue(result: TransactionFilters, val: string): void {
  if (val === 'uncategorized') result.uncategorized = true
  else if (val === 'unapproved') result.unapproved = true
  else if (val === 'transfer') result.isTransfer = true
  else if (val === 'unpaired') result.unpairedTransfers = true
  else if (DIRECTION_VALUES.has(val)) result.direction = val as 'inflow' | 'outflow'
  else if (CLEARED_VALUES.has(val)) result.cleared = val
}

function isRecognizedIsValue(val: string): boolean {
  return (
    val === 'uncategorized' ||
    val === 'unapproved' ||
    val === 'transfer' ||
    val === 'unpaired' ||
    DIRECTION_VALUES.has(val) ||
    CLEARED_VALUES.has(val)
  )
}

function parseSegment(
  tokens: string[],
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>,
  accountMap: Map<string, string>,
  now: Date
): TransactionFilters {
  const result: TransactionFilters = {}
  const textParts: string[] = []

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const lower = token.toLowerCase()

    // is: value  (space-separated)  or  is:value  (compact)
    if (lower === 'is:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val && isRecognizedIsValue(val)) { applyIsValue(result, val); i++ }
      continue
    }
    const isMatch = lower.match(/^is:(\w+)$/)
    if (isMatch) {
      applyIsValue(result, isMatch[1])
      continue
    }

    // has: attachment  (space-separated)  or  has:attachment (compact) —
    // 'image' and 'receipt' accepted as synonyms
    if (lower === 'has:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val && ATTACHMENT_VALUES.has(val)) { result.hasAttachment = true; i++; continue }
      continue
    }
    const hasMatch = lower.match(/^has:(\w+)$/)
    if (hasMatch) {
      if (ATTACHMENT_VALUES.has(hasMatch[1])) result.hasAttachment = true
      continue
    }

    // category: value  or  category:value
    const catPrefix = lower === 'category:' ? tokens[i + 1] : lower.match(/^category:(.+)$/)?.[1]
    if (catPrefix !== undefined) {
      if (lower === 'category:') i++
      const catQuery = catPrefix.replace(/^"|"$/g, '').toLowerCase()
      const ids: string[] = []
      for (const [id, name] of categoryMap) {
        if (name.toLowerCase().includes(catQuery)) ids.push(id)
      }
      if (ids.length) result.categoryIds = ids
      continue
    }

    // payee: value  or  payee:value
    const payeePrefix = lower === 'payee:' ? tokens[i + 1] : lower.match(/^payee:(.+)$/)?.[1]
    if (payeePrefix !== undefined) {
      if (lower === 'payee:') i++
      const payeeQuery = payeePrefix.replace(/^"|"$/g, '').toLowerCase()
      const ids: string[] = []
      for (const [id, name] of payeeMap) {
        if (name.toLowerCase().includes(payeeQuery)) ids.push(id)
      }
      if (ids.length) result.payeeIds = ids
      continue
    }

    // account: value  or  account:value — resolvable only where the caller
    // provides an account map (the all-accounts register); otherwise the
    // token falls through to free text
    const accountPrefix = lower === 'account:' ? tokens[i + 1] : lower.match(/^account:(.+)$/)?.[1]
    if (accountPrefix !== undefined && accountMap.size > 0) {
      if (lower === 'account:') i++
      const accountQuery = accountPrefix.replace(/^"|"$/g, '').toLowerCase()
      const ids: string[] = []
      for (const [id, name] of accountMap) {
        if (name.toLowerCase().includes(accountQuery)) ids.push(id)
      }
      if (ids.length) result.accountIds = ids
      continue
    }

    // amount:>x  amount:<x  amount:x-y
    const amountExpr = lower === 'amount:' ? tokens[i + 1] : lower.match(/^amount:(.+)$/)?.[1]
    if (amountExpr !== undefined) {
      if (lower === 'amount:') i++
      if (amountExpr?.startsWith('>')) result.amountMin = parseFloat(amountExpr.slice(1))
      else if (amountExpr?.startsWith('<')) result.amountMax = parseFloat(amountExpr.slice(1))
      else {
        const range = amountExpr?.match(/^([\d.]+)-([\d.]+)$/)
        if (range) { result.amountMin = parseFloat(range[1]); result.amountMax = parseFloat(range[2]) }
        else {
          // Bare value is an exact amount — a zero-width range
          const exact = amountExpr?.match(/^\$?([\d,]*\.?\d+)$/)
          if (exact) {
            const value = parseFloat(exact[1].replace(/,/g, ''))
            if (!isNaN(value)) { result.amountMin = value; result.amountMax = value }
          }
        }
      }
      continue
    }

    // date: 3/15 · date:>3/1 · date: 3/1-3/15 · date: last month
    const dateFilter = matchDateFilterToken(tokens, i, now)
    if (dateFilter) {
      if (dateFilter.startDate) result.startDate = dateFilter.startDate
      if (dateFilter.endDate) result.endDate = dateFilter.endDate
      i += dateFilter.consumed - 1
      continue
    }
    if (lower === 'date:' || lower.startsWith('date:')) {
      // Unparseable date token — swallow it rather than searching for "date:"
      if (lower === 'date:') i++
      continue
    }

    // Natural-language date tokens: today, yesterday, last week, march…
    const dateMatch = matchDateTokens(tokens, i, now)
    if (dateMatch) {
      result.startDate = dateMatch.startDate
      result.endDate = dateMatch.endDate
      i += dateMatch.consumed - 1
      continue
    }

    textParts.push(token)
  }

  const text = textParts.join(' ').trim()
  if (text) result.text = text
  return result
}

function mergeWithOr(segments: TransactionFilters[]): TransactionFilters {
  const merged: TransactionFilters = { isOrMode: true }
  const textParts: string[] = []
  const allCategoryIds: string[] = []
  const allPayeeIds: string[] = []
  const allAccountIds: string[] = []

  for (const seg of segments) {
    if (seg.unapproved) merged.unapproved = true
    if (seg.uncategorized) merged.uncategorized = true
    if (seg.unpairedTransfers) merged.unpairedTransfers = true
    if (seg.cleared) merged.cleared = seg.cleared
    if (seg.text) textParts.push(seg.text)
    if (seg.categoryIds) allCategoryIds.push(...seg.categoryIds)
    if (seg.payeeIds) allPayeeIds.push(...seg.payeeIds)
    if (seg.accountIds) allAccountIds.push(...seg.accountIds)
    if (seg.amountMin != null) merged.amountMin = seg.amountMin
    if (seg.amountMax != null) merged.amountMax = seg.amountMax
    if (seg.hasAttachment != null) merged.hasAttachment = seg.hasAttachment
    if (seg.startDate != null) merged.startDate = seg.startDate
    if (seg.endDate != null) merged.endDate = seg.endDate
    if (seg.direction != null) merged.direction = seg.direction
    if (seg.isTransfer != null) merged.isTransfer = seg.isTransfer
  }

  if (textParts.length) merged.text = textParts.join(' ')
  if (allCategoryIds.length) merged.categoryIds = allCategoryIds
  if (allPayeeIds.length) merged.payeeIds = allPayeeIds
  if (allAccountIds.length) merged.accountIds = allAccountIds

  return merged
}

export function parseTransactionSearch(
  query: string,
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>,
  accountMap: Map<string, string> = new Map(),
  now: Date = new Date()
): TransactionFilters {
  const tokens = tokenize(query)

  // Extract NOT modifiers globally before OR splitting — they apply to all results
  const exclusions: TransactionFilters = {}
  const positiveTokens: string[] = []

  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].toUpperCase() === 'NOT') {
      i++
      if (i >= tokens.length) continue
      const next = tokens[i]
      const nextLower = next.toLowerCase()

      // NOT is: value  (space-separated)
      if (nextLower === 'is:') {
        const val = tokens[i + 1]?.toLowerCase()
        if (val && CLEARED_VALUES.has(val)) { exclusions.excludeCleared = val; i++ }
        else if (val === 'transfer') { exclusions.isTransfer = false; i++ }
        continue
      }
      // NOT is:value  (compact)
      const isMatch = nextLower.match(/^is:(\w+)$/)
      if (isMatch && CLEARED_VALUES.has(isMatch[1])) {
        exclusions.excludeCleared = isMatch[1]
        continue
      }
      if (isMatch && isMatch[1] === 'transfer') {
        exclusions.isTransfer = false
        continue
      }
      // NOT has: attachment — rows without an image
      if (nextLower === 'has:') {
        const val = tokens[i + 1]?.toLowerCase()
        if (val && ATTACHMENT_VALUES.has(val)) { exclusions.hasAttachment = false; i++ }
        continue
      }
      const hasMatch = nextLower.match(/^has:(\w+)$/)
      if (hasMatch && ATTACHMENT_VALUES.has(hasMatch[1])) {
        exclusions.hasAttachment = false
        continue
      }
      // Unrecognised NOT — pass both tokens through as text
      positiveTokens.push('NOT', tokens[i])
    } else {
      positiveTokens.push(tokens[i])
    }
  }

  // Split remaining tokens at OR keyword into segments
  const segments: string[][] = []
  let current: string[] = []
  for (const token of positiveTokens) {
    if (token.toUpperCase() === 'OR') {
      segments.push(current)
      current = []
    } else {
      current.push(token)
    }
  }
  segments.push(current)

  const parsed = segments.map((seg) => parseSegment(seg, categoryMap, payeeMap, accountMap, now))
  const positive = parsed.length === 1 ? parsed[0] : mergeWithOr(parsed)

  return Object.keys(exclusions).length ? { ...positive, ...exclusions } : positive
}

function tokenize(query: string): string[] {
  const tokens: string[] = []
  let i = 0
  while (i < query.length) {
    if (query[i] === '"') {
      let j = i + 1
      while (j < query.length && query[j] !== '"') j++
      tokens.push(query.slice(i, j + 1))
      i = j + 1
    } else if (query[i] === ' ') {
      i++
    } else {
      let j = i
      while (j < query.length && query[j] !== ' ') j++
      tokens.push(query.slice(i, j))
      i = j
    }
  }
  return tokens.filter(Boolean)
}

export const SEARCH_SUGGESTIONS = [
  { syntax: 'is: unapproved ', description: 'Transactions not yet approved' },
  { syntax: 'is: uncategorized ', description: 'Transactions without a category' },
  { syntax: 'is: cleared ', description: 'Cleared transactions' },
  { syntax: 'is: uncleared ', description: 'Uncleared transactions' },
  { syntax: 'is: pending ', description: 'Pending transactions' },
  { syntax: 'is: reconciled ', description: 'Reconciled transactions' },
  { syntax: 'is: inflow ', description: 'Money in (positive amounts)' },
  { syntax: 'is: outflow ', description: 'Money out (negative amounts)' },
  { syntax: 'is: transfer ', description: 'Transfers between accounts' },
  { syntax: 'is: unpaired ', description: "Transfers whose other side never arrived" },
  { syntax: 'has: attachment ', description: 'Transactions with an image attached' },
  { syntax: 'NOT has: attachment ', description: 'Transactions without an image' },
  { syntax: 'category:', description: 'Filter by category name' },
  { syntax: 'payee:', description: 'Filter by payee name' },
  { syntax: 'amount: ', description: 'Exact amount or range (amount: 12.34, amount: 10-20) — typing 12.34 alone works too' },
  { syntax: 'amount:>', description: 'Amount greater than (e.g. amount:>100)' },
  { syntax: 'amount:<', description: 'Amount less than (e.g. amount:<50)' },
  { syntax: 'date: ', description: 'On a date or range (date: 3/15, date: 3/1-3/15, date: 2025-03-15)' },
  { syntax: 'date:>', description: 'On or after a date (e.g. date:>3/1)' },
  { syntax: 'date:<', description: 'On or before a date (e.g. date:<3/15)' },
  { syntax: 'today ', description: 'Dated today (also: yesterday, last week, last month)' },
  { syntax: 'last month ', description: 'Dated in the previous calendar month' },
  { syntax: 'march ', description: 'Dated in a month (add a year: march 2025, or a range: jan-mar)' },
  { syntax: 'OR', description: 'Combine filters with OR logic (e.g. is: unapproved OR is: uncategorized)' },
  { syntax: 'NOT is: pending ', description: 'Exclude pending transactions (global, works with OR)' },
  { syntax: 'NOT is: transfer ', description: 'Exclude transfers' },
]

export interface SearchChip {
  /** Stable identity for React keys */
  key: string
  label: string
  /** Indices into tokenize(query) that this chip owns */
  indices: number[]
}

const IS_LABELS: Record<string, string> = {
  uncategorized: 'Uncategorized',
  unapproved: 'Unapproved',
  cleared: 'Cleared',
  uncleared: 'Uncleared',
  pending: 'Pending',
  reconciled: 'Reconciled',
  inflow: 'Inflow',
  outflow: 'Outflow',
  transfer: 'Transfer',
}

function stripQuotes(s: string): string {
  return s.replace(/^"|"$/g, '')
}

/**
 * Describe each recognised filter construct in the query as a removable
 * chip. Mirrors parseTransactionSearch's token recognition; free text and
 * OR keywords produce no chips. Remove a chip with removeSearchChip.
 */
export function describeSearchChips(
  query: string,
  accountMapSize = 0,
  now: Date = new Date()
): SearchChip[] {
  const tokens = tokenize(query)
  const chips: SearchChip[] = []
  const push = (label: string, indices: number[]) =>
    chips.push({ key: `${indices[0]}:${label}`, label, indices })

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const lower = token.toLowerCase()

    if (token.toUpperCase() === 'NOT') {
      const nextLower = tokens[i + 1]?.toLowerCase()
      if (nextLower === 'is:' || nextLower === 'has:') {
        const val = tokens[i + 2]?.toLowerCase()
        if (nextLower === 'is:' && val && (CLEARED_VALUES.has(val) || val === 'transfer')) {
          push(`Not ${val}`, [i, i + 1, i + 2])
          i += 2
        } else if (nextLower === 'has:' && val && ATTACHMENT_VALUES.has(val)) {
          push('No attachment', [i, i + 1, i + 2])
          i += 2
        }
        continue
      }
      const isMatch = nextLower?.match(/^is:(\w+)$/)
      if (isMatch && (CLEARED_VALUES.has(isMatch[1]) || isMatch[1] === 'transfer')) {
        push(`Not ${isMatch[1]}`, [i, i + 1])
        i++
        continue
      }
      const hasMatch = nextLower?.match(/^has:(\w+)$/)
      if (hasMatch && ATTACHMENT_VALUES.has(hasMatch[1])) {
        push('No attachment', [i, i + 1])
        i++
      }
      continue
    }

    if (lower === 'is:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val && isRecognizedIsValue(val)) {
        push(IS_LABELS[val], [i, i + 1])
        i++
      }
      continue
    }
    const isMatch = lower.match(/^is:(\w+)$/)
    if (isMatch) {
      if (isRecognizedIsValue(isMatch[1])) push(IS_LABELS[isMatch[1]], [i])
      continue
    }

    if (lower === 'has:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val && ATTACHMENT_VALUES.has(val)) {
        push('Has attachment', [i, i + 1])
        i++
      }
      continue
    }
    const hasMatch = lower.match(/^has:(\w+)$/)
    if (hasMatch) {
      if (ATTACHMENT_VALUES.has(hasMatch[1])) push('Has attachment', [i])
      continue
    }

    const dateFilter = matchDateFilterToken(tokens, i, now)
    if (dateFilter) {
      const indices = Array.from({ length: dateFilter.consumed }, (_, k) => i + k)
      push(dateFilter.label, indices)
      i += dateFilter.consumed - 1
      continue
    }

    let prefixMatched = false
    for (const [prefix, chipLabel] of [
      ['category:', 'Category'],
      ['payee:', 'Payee'],
      ['account:', 'Account'],
      ['amount:', 'Amount'],
    ] as const) {
      // account: only resolves on the all-accounts register (mirrors parser)
      if (prefix === 'account:' && accountMapSize === 0) continue
      const spaced = lower === prefix
      const value = spaced
        ? tokens[i + 1]
        : lower.startsWith(prefix)
          ? token.slice(prefix.length)
          : undefined
      if (!value) continue
      push(`${chipLabel}: ${stripQuotes(value)}`, spaced ? [i, i + 1] : [i])
      if (spaced) i++
      prefixMatched = true
      break
    }
    if (prefixMatched) continue

    const dateMatch = matchDateTokens(tokens, i, now)
    if (dateMatch) {
      const indices = Array.from({ length: dateMatch.consumed }, (_, k) => i + k)
      push(dateMatch.label, indices)
      i += dateMatch.consumed - 1
    }
  }

  return chips
}

/**
 * Rebuild the query with a chip's tokens removed. ORs left dangling at
 * the edges or doubled up by the removal are dropped too.
 */
export function removeSearchChip(query: string, chip: SearchChip): string {
  const drop = new Set(chip.indices)
  const kept = tokenize(query).filter((_, idx) => !drop.has(idx))
  const cleaned = kept.filter((t, idx) => {
    if (t.toUpperCase() !== 'OR') return true
    const prev = kept[idx - 1]
    const next = kept[idx + 1]
    return !!prev && !!next && prev.toUpperCase() !== 'OR' && next.toUpperCase() !== 'OR'
  })
  return cleaned.join(' ')
}
