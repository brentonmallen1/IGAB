import type { Transaction, ClearedStatus } from '../types'

export interface ParsedSearch {
  text: string
  clearedStatuses: ClearedStatus[]
  categoryIds: string[]
  payeeIds: string[]
  amountMin: number | null
  amountMax: number | null
}

const CLEARED_ALIASES: Record<string, ClearedStatus> = {
  cleared: 'cleared',
  uncleared: 'uncleared',
  pending: 'pending',
  reconciled: 'reconciled',
}

export function parseTransactionSearch(
  query: string,
  categoryMap: Map<string, string>,
  payeeMap: Map<string, string>
): ParsedSearch {
  const result: ParsedSearch = {
    text: '',
    clearedStatuses: [],
    categoryIds: [],
    payeeIds: [],
    amountMin: null,
    amountMax: null,
  }

  const tokens = tokenize(query)
  const textParts: string[] = []

  for (const token of tokens) {
    const lower = token.toLowerCase()

    // is:cleared / is:uncleared / is:pending / is:reconciled
    const isMatch = lower.match(/^is:(\w+)$/)
    if (isMatch) {
      const status = CLEARED_ALIASES[isMatch[1]]
      if (status) result.clearedStatuses.push(status)
      continue
    }

    // category:"name" or category:name
    const catMatch = lower.match(/^category:(.+)$/)
    if (catMatch) {
      const catQuery = catMatch[1].replace(/^"|"$/g, '').toLowerCase()
      for (const [id, name] of categoryMap) {
        if (name.toLowerCase().includes(catQuery)) result.categoryIds.push(id)
      }
      continue
    }

    // payee:"name" or payee:name
    const payeeMatch = lower.match(/^payee:(.+)$/)
    if (payeeMatch) {
      const payeeQuery = payeeMatch[1].replace(/^"|"$/g, '').toLowerCase()
      for (const [id, name] of payeeMap) {
        if (name.toLowerCase().includes(payeeQuery)) result.payeeIds.push(id)
      }
      continue
    }

    // amount:>100 or amount:<50 or amount:100-200
    const amountMatch = lower.match(/^amount:(.+)$/)
    if (amountMatch) {
      const expr = amountMatch[1]
      if (expr.startsWith('>')) result.amountMin = parseFloat(expr.slice(1))
      else if (expr.startsWith('<')) result.amountMax = parseFloat(expr.slice(1))
      else {
        const range = expr.match(/^([\d.]+)-([\d.]+)$/)
        if (range) {
          result.amountMin = parseFloat(range[1])
          result.amountMax = parseFloat(range[2])
        }
      }
      continue
    }

    textParts.push(token)
  }

  result.text = textParts.join(' ').trim()
  return result
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

export function filterTransactions(
  transactions: Transaction[],
  search: ParsedSearch,
  payeeMap: Map<string, string>
): Transaction[] {
  return transactions.filter((txn) => {
    if (search.clearedStatuses.length > 0 && !search.clearedStatuses.includes(txn.cleared)) {
      return false
    }

    if (search.categoryIds.length > 0 && !search.categoryIds.includes(txn.category_id ?? '')) {
      return false
    }

    if (search.payeeIds.length > 0 && !search.payeeIds.includes(txn.payee_id ?? '')) {
      return false
    }

    const absAmount = Math.abs(Number(txn.amount))
    if (search.amountMin !== null && absAmount < search.amountMin) return false
    if (search.amountMax !== null && absAmount > search.amountMax) return false

    if (search.text) {
      const q = search.text.toLowerCase()
      const payeeName = (txn.payee_id ? payeeMap.get(txn.payee_id) : '') ?? ''
      const memo = txn.memo ?? ''
      if (!payeeName.toLowerCase().includes(q) && !memo.toLowerCase().includes(q)) {
        return false
      }
    }

    return true
  })
}

export const SEARCH_SUGGESTIONS = [
  { syntax: 'is:cleared', description: 'Show cleared transactions' },
  { syntax: 'is:uncleared', description: 'Show uncleared transactions' },
  { syntax: 'is:pending', description: 'Show pending transactions' },
  { syntax: 'is:reconciled', description: 'Show reconciled transactions' },
  { syntax: 'category:', description: 'Filter by category name' },
  { syntax: 'payee:', description: 'Filter by payee name' },
  { syntax: 'amount:>100', description: 'Amount greater than' },
  { syntax: 'amount:<50', description: 'Amount less than' },
]
