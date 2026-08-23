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
  origin: number[],
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>,
  accountMap: Map<string, string>,
  now: Date,
  chips: SearchChip[],
  literal: ReadonlySet<number>
): TransactionFilters {
  const result: TransactionFilters = {}
  const textParts: string[] = []
  // A chip is emitted only where a filter was actually applied. The chips used
  // to be produced by a second walk over the same tokens, and it disagreed:
  // `category: zzz` matching nothing applied no filter but still drew a
  // "Category: zzz" chip, so the register showed a filter it was not applying.
  const emit = (label: string, from: number, count = 1) =>
    chips.push({
      key: `${origin[from]}:${label}`,
      label,
      indices: origin.slice(from, from + count),
    })

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const lower = token.toLowerCase()

    // Tokens an unrecognised NOT owns. They are searched as text and must not
    // be recognised again here: `NOT is:uncategorized` used to drop the NOT
    // and apply `is:uncategorized` positively — the opposite of the ask.
    if (literal.has(origin[i])) {
      textParts.push(token)
      continue
    }

    // is: value  (space-separated)  or  is:value  (compact)
    if (lower === 'is:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val && isRecognizedIsValue(val)) {
        applyIsValue(result, val)
        emit(IS_LABELS[val], i, 2)
        i++
      }
      continue
    }
    const isMatch = lower.match(/^is:(\w+)$/)
    if (isMatch && isRecognizedIsValue(isMatch[1])) {
      applyIsValue(result, isMatch[1])
      emit(IS_LABELS[isMatch[1]], i)
      continue
    }
    if (isMatch) {
      // Unrecognised `is:` was swallowed here — no filter, no chip, and the
      // token invisible. Falling through searches for it as text instead.
      textParts.push(token)
      continue
    }

    // has: attachment  (space-separated)  or  has:attachment (compact) —
    // 'image' and 'receipt' accepted as synonyms
    if (lower === 'has:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val && ATTACHMENT_VALUES.has(val)) {
        result.hasAttachment = true
        emit('Has attachment', i, 2)
        i++
        continue
      }
      continue
    }
    const hasMatch = lower.match(/^has:(\w+)$/)
    if (hasMatch) {
      if (ATTACHMENT_VALUES.has(hasMatch[1])) {
        result.hasAttachment = true
        emit('Has attachment', i)
      }
      continue
    }

    // category: value  or  category:value
    const catPrefix = lower === 'category:' ? tokens[i + 1] : lower.match(/^category:(.+)$/)?.[1]
    if (catPrefix !== undefined) {
      const start = i
      const spaced = lower === 'category:'
      if (spaced) i++
      const catQuery = catPrefix.replace(/^"|"$/g, '').toLowerCase()
      const ids: string[] = []
      for (const [id, name] of categoryMap) {
        if (name.toLowerCase().includes(catQuery)) ids.push(id)
      }
      if (ids.length) {
        result.categoryIds = ids
        emit(`Category: ${catQuery}`, start, spaced ? 2 : 1)
      }
      continue
    }

    // payee: value  or  payee:value
    const payeePrefix = lower === 'payee:' ? tokens[i + 1] : lower.match(/^payee:(.+)$/)?.[1]
    if (payeePrefix !== undefined) {
      const start = i
      const spaced = lower === 'payee:'
      if (spaced) i++
      const payeeQuery = payeePrefix.replace(/^"|"$/g, '').toLowerCase()
      const ids: string[] = []
      for (const [id, name] of payeeMap) {
        if (name.toLowerCase().includes(payeeQuery)) ids.push(id)
      }
      if (ids.length) {
        result.payeeIds = ids
        emit(`Payee: ${payeeQuery}`, start, spaced ? 2 : 1)
      }
      continue
    }

    // account: value  or  account:value — resolvable only where the caller
    // provides an account map (the all-accounts register); otherwise the
    // token falls through to free text
    const accountPrefix = lower === 'account:' ? tokens[i + 1] : lower.match(/^account:(.+)$/)?.[1]
    if (accountPrefix !== undefined && accountMap.size > 0) {
      const start = i
      const spaced = lower === 'account:'
      if (spaced) i++
      const accountQuery = accountPrefix.replace(/^"|"$/g, '').toLowerCase()
      const ids: string[] = []
      for (const [id, name] of accountMap) {
        if (name.toLowerCase().includes(accountQuery)) ids.push(id)
      }
      if (ids.length) {
        result.accountIds = ids
        emit(`Account: ${accountQuery}`, start, spaced ? 2 : 1)
      }
      continue
    }

    // amount:>x  amount:<x  amount:x-y
    const amountExpr = lower === 'amount:' ? tokens[i + 1] : lower.match(/^amount:(.+)$/)?.[1]
    if (amountExpr !== undefined) {
      const start = i
      const spaced = lower === 'amount:'
      if (spaced) i++
      let recognised = true
      if (amountExpr?.startsWith('>')) result.amountMin = parseFloat(amountExpr.slice(1))
      else if (amountExpr?.startsWith('<')) result.amountMax = parseFloat(amountExpr.slice(1))
      else {
        const range = amountExpr?.match(/^([\d.]+)-([\d.]+)$/)
        if (range) { result.amountMin = parseFloat(range[1]); result.amountMax = parseFloat(range[2]) }
        else {
          // Bare value is an exact amount — a zero-width range.
          // A TRAILING dot is accepted ("12." → 12): it is a half-typed
          // amount, and rejecting it blanked the register mid-keystroke,
          // which reads as "typing a dot breaks search". Kept in step with
          // _AMOUNT_SEARCH_RE in backend/repositories/transaction_repo.py —
          // irreducible duplication (this one runs before any round-trip),
          // so both suites carry the same cases: 12, 12., 12.34, .34, $1,200.
          const exact = amountExpr?.match(/^\$?([\d,]+\.?\d*|[\d,]*\.\d+)$/)
          if (exact) {
            const value = parseFloat(exact[1].replace(/,/g, ''))
            if (!isNaN(value)) { result.amountMin = value; result.amountMax = value }
            else recognised = false
          } else recognised = false
        }
      }
      // `amount: abc` filtered nothing but still drew an "Amount: abc" chip.
      if (recognised) emit(`Amount: ${amountExpr}`, start, spaced ? 2 : 1)
      continue
    }

    // date: 3/15 · date:>3/1 · date: 3/1-3/15 · date: last month
    const dateFilter = matchDateFilterToken(tokens, i, now)
    if (dateFilter) {
      if (dateFilter.startDate) result.startDate = dateFilter.startDate
      if (dateFilter.endDate) result.endDate = dateFilter.endDate
      emit(dateFilter.label, i, dateFilter.consumed)
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
      emit(dateMatch.label, i, dateMatch.consumed)
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

interface ParsedSearch {
  filters: TransactionFilters
  chips: SearchChip[]
}

/**
 * One walk over the tokens, producing both the filters and the chips.
 *
 * `describeSearchChips` used to be a second walk carrying its own copy of
 * every recognizer, self-described as "mirrors parseTransactionSearch's token
 * recognition". The two disagreed, and the chips were the half that lied: a
 * `category:` matching nothing drew a chip while filtering nothing, and a
 * `NOT` the parser could not read became a free-text search with no chip to
 * say so. Chips are a projection of what was recognised now, so a chip exists
 * exactly when a filter does.
 *
 * Token indices are carried through the NOT extraction and the OR split so a
 * chip can still name the tokens it owns — `removeSearchChip` needs them.
 */
function parseSearch(
  query: string,
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>,
  accountMap: Map<string, string>,
  now: Date
): ParsedSearch {
  const tokens = tokenize(query)
  const chips: SearchChip[] = []
  const emit = (label: string, indices: number[]) =>
    chips.push({ key: `${indices[0]}:${label}`, label, indices })

  // Extract NOT modifiers globally before OR splitting — they apply to all results
  const exclusions: TransactionFilters = {}
  const positiveTokens: string[] = []
  const positiveIdx: number[] = []
  const literal = new Set<number>()
  const keep = (idx: number) => {
    positiveTokens.push(tokens[idx])
    positiveIdx.push(idx)
  }

  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].toUpperCase() === 'NOT') {
      const notAt = i
      i++
      if (i >= tokens.length) continue
      const next = tokens[i]
      const nextLower = next.toLowerCase()

      // NOT is: value  (space-separated)
      if (nextLower === 'is:') {
        const val = tokens[i + 1]?.toLowerCase()
        if (val && CLEARED_VALUES.has(val)) {
          exclusions.excludeCleared = val
          emit(`Not ${val}`, [notAt, i, i + 1])
          i++
        } else if (val === 'transfer') {
          exclusions.isTransfer = false
          emit('Not transfer', [notAt, i, i + 1])
          i++
        }
        continue
      }
      // NOT is:value  (compact)
      const isMatch = nextLower.match(/^is:(\w+)$/)
      if (isMatch && CLEARED_VALUES.has(isMatch[1])) {
        exclusions.excludeCleared = isMatch[1]
        emit(`Not ${isMatch[1]}`, [notAt, i])
        continue
      }
      if (isMatch && isMatch[1] === 'transfer') {
        exclusions.isTransfer = false
        emit('Not transfer', [notAt, i])
        continue
      }
      // NOT has: attachment — rows without an image
      if (nextLower === 'has:') {
        const val = tokens[i + 1]?.toLowerCase()
        if (val && ATTACHMENT_VALUES.has(val)) {
          exclusions.hasAttachment = false
          emit('No attachment', [notAt, i, i + 1])
          i++
        }
        continue
      }
      const hasMatch = nextLower.match(/^has:(\w+)$/)
      if (hasMatch && ATTACHMENT_VALUES.has(hasMatch[1])) {
        exclusions.hasAttachment = false
        emit('No attachment', [notAt, i])
        continue
      }
      // Unrecognised NOT — pass both tokens through as text, and draw no chip.
      // The register really is doing a text search for them. Marking them
      // literal is what makes that true: without it the second token was
      // recognised again downstream and the filter applied *positively*.
      literal.add(notAt)
      literal.add(i)
      keep(notAt)
      keep(i)
    } else {
      keep(i)
    }
  }

  // Split remaining tokens at OR keyword into segments, keeping origins
  const segments: number[][] = []
  let current: number[] = []
  for (let k = 0; k < positiveTokens.length; k++) {
    if (positiveTokens[k].toUpperCase() === 'OR') {
      segments.push(current)
      current = []
    } else {
      current.push(positiveIdx[k])
    }
  }
  segments.push(current)

  const parsed = segments.map((origin) =>
    parseSegment(
      origin.map((idx) => tokens[idx]),
      origin,
      categoryMap,
      payeeMap,
      accountMap,
      now,
      chips,
      literal
    )
  )
  const positive = parsed.length === 1 ? parsed[0] : mergeWithOr(parsed)

  return {
    filters: Object.keys(exclusions).length ? { ...positive, ...exclusions } : positive,
    chips: chips.sort((a, b) => a.indices[0] - b.indices[0]),
  }
}

export function parseTransactionSearch(
  query: string,
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>,
  accountMap: Map<string, string> = new Map(),
  now: Date = new Date()
): TransactionFilters {
  return parseSearch(query, categoryMap, payeeMap, accountMap, now).filters
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

export interface MatchedSuggestion {
  syntax: string
  description: string
  /** How many characters at the end of the query this suggestion completes,
   *  so accepting it replaces exactly that much and nothing the user typed
   *  before it. */
  matchedLen: number
}

/**
 * The suggestions worth offering for a half-typed query.
 *
 * Syntaxes span several tokens ("is: unapproved", "NOT has: attachment"), so
 * this matches a trailing RUN of tokens rather than the last word alone —
 * otherwise the list empties the moment a user types the space in "is: ".
 *
 * Shared by the register's search box and the command palette: one place that
 * decides what the search language advertises, so the palette cannot quietly
 * offer a smaller vocabulary than the box that taught it.
 */
export function matchSuggestions(query: string): MatchedSuggestion[] {
  const tokens = query.trimEnd() ? query.trimEnd().split(' ') : []
  if (tokens.length === 0) return SEARCH_SUGGESTIONS.map((s) => ({ ...s, matchedLen: 0 }))
  return SEARCH_SUGGESTIONS.map((s) => {
    const lower = s.syntax.toLowerCase()
    let matchedLen = 0
    for (let n = Math.min(3, tokens.length); n >= 1; n--) {
      const tail = tokens.slice(-n).join(' ')
      if (lower.startsWith(tail.toLowerCase())) {
        matchedLen = tail.length
        break
      }
    }
    return { ...s, matchedLen }
  }).filter((s) => s.matchedLen > 0)
}

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

/**
 * Describe each recognised filter construct in the query as a removable
 * chip. Mirrors parseTransactionSearch's token recognition; free text and
 * OR keywords produce no chips. Remove a chip with removeSearchChip.
 */
/**
 * Removable chips for each filter the parser actually recognised.
 *
 * Takes the same maps the parser takes, because a chip can only be honest
 * about `category:`/`payee:`/`account:` if it knows whether those resolved.
 * The old signature took only `accountMapSize`, which is why it had to
 * re-implement recognition and why it could not tell a match from a miss.
 */
export function describeSearchChips(
  query: string,
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>,
  accountMap: Map<string, string> = new Map(),
  now: Date = new Date()
): SearchChip[] {
  return parseSearch(query, categoryMap, payeeMap, accountMap, now).chips
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
