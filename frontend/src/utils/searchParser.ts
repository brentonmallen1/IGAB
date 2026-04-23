export interface TransactionFilters {
  text?: string
  cleared?: string
  uncategorized?: boolean
  unapproved?: boolean
  categoryIds?: string[]
  payeeIds?: string[]
  amountMin?: number | null
  amountMax?: number | null
  isOrMode?: boolean
}

export function hasActiveFilters(f: TransactionFilters): boolean {
  return !!(
    f.text ||
    f.cleared ||
    f.uncategorized ||
    f.unapproved ||
    (f.categoryIds?.length ?? 0) > 0 ||
    (f.payeeIds?.length ?? 0) > 0 ||
    f.amountMin != null ||
    f.amountMax != null
  )
}

const CLEARED_VALUES = new Set(['cleared', 'uncleared', 'pending', 'reconciled'])

function parseSegment(
  tokens: string[],
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>
): TransactionFilters {
  const result: TransactionFilters = {}
  const textParts: string[] = []

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const lower = token.toLowerCase()

    // is: value  (space-separated)  or  is:value  (compact)
    if (lower === 'is:') {
      const val = tokens[i + 1]?.toLowerCase()
      if (val === 'uncategorized') { result.uncategorized = true; i++; continue }
      if (val === 'unapproved') { result.unapproved = true; i++; continue }
      if (val && CLEARED_VALUES.has(val)) { result.cleared = val; i++; continue }
      continue
    }
    const isMatch = lower.match(/^is:(\w+)$/)
    if (isMatch) {
      if (isMatch[1] === 'uncategorized') result.uncategorized = true
      else if (isMatch[1] === 'unapproved') result.unapproved = true
      else if (CLEARED_VALUES.has(isMatch[1])) result.cleared = isMatch[1]
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

    // amount:>x  amount:<x  amount:x-y
    const amountExpr = lower === 'amount:' ? tokens[i + 1] : lower.match(/^amount:(.+)$/)?.[1]
    if (amountExpr !== undefined) {
      if (lower === 'amount:') i++
      if (amountExpr?.startsWith('>')) result.amountMin = parseFloat(amountExpr.slice(1))
      else if (amountExpr?.startsWith('<')) result.amountMax = parseFloat(amountExpr.slice(1))
      else {
        const range = amountExpr?.match(/^([\d.]+)-([\d.]+)$/)
        if (range) { result.amountMin = parseFloat(range[1]); result.amountMax = parseFloat(range[2]) }
      }
      continue
    }

    textParts.push(token)
  }

  const text = textParts.join(' ').trim()
  if (text) result.text = text
  return result
}

export function parseTransactionSearch(
  query: string,
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>
): TransactionFilters {
  const tokens = tokenize(query)

  // Split at OR keyword into segments
  const segments: string[][] = []
  let current: string[] = []
  for (const token of tokens) {
    if (token.toUpperCase() === 'OR') {
      segments.push(current)
      current = []
    } else {
      current.push(token)
    }
  }
  segments.push(current)

  const parsed = segments.map((seg) => parseSegment(seg, categoryMap, payeeMap))
  if (parsed.length === 1) return parsed[0]

  // Merge multiple segments with OR semantics
  const merged: TransactionFilters = { isOrMode: true }
  const textParts: string[] = []
  const allCategoryIds: string[] = []
  const allPayeeIds: string[] = []

  for (const seg of parsed) {
    if (seg.unapproved) merged.unapproved = true
    if (seg.uncategorized) merged.uncategorized = true
    if (seg.cleared) merged.cleared = seg.cleared
    if (seg.text) textParts.push(seg.text)
    if (seg.categoryIds) allCategoryIds.push(...seg.categoryIds)
    if (seg.payeeIds) allPayeeIds.push(...seg.payeeIds)
    if (seg.amountMin != null) merged.amountMin = seg.amountMin
    if (seg.amountMax != null) merged.amountMax = seg.amountMax
  }

  if (textParts.length) merged.text = textParts.join(' ')
  if (allCategoryIds.length) merged.categoryIds = allCategoryIds
  if (allPayeeIds.length) merged.payeeIds = allPayeeIds

  return merged
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
  { syntax: 'category:', description: 'Filter by category name' },
  { syntax: 'payee:', description: 'Filter by payee name' },
  { syntax: 'amount:>', description: 'Amount greater than (e.g. amount:>100)' },
  { syntax: 'amount:<', description: 'Amount less than (e.g. amount:<50)' },
  { syntax: 'OR', description: 'Combine filters with OR logic (e.g. is: unapproved OR is: uncategorized)' },
]
