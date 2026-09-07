import type { CsvMapping } from '../../../api/imports'

/**
 * What you said this account's export looks like, last time.
 *
 * Per account, because the file is that account's own export: next month's
 * download from the same bank has the same headers, and re-answering the
 * mapping every month is the sort of small tax that stops people importing
 * at all.
 *
 * Deliberately local to the browser rather than a column on the account.
 * A remembered guess is a convenience, not a fact about the budget — losing
 * it costs one mapping step, and storing it server-side would mean a schema
 * for something the user can always correct in front of them. The YNAB
 * importer's `ImportAccountMapping` earns its table by deciding where money
 * lands; this only pre-fills a form.
 */
const KEY = 'igab.csvMapping'

type Store = Record<string, CsvMapping>

function read(): Store {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Store) : {}
  } catch {
    // A private window, cleared site data, or storage the browser refuses.
    // Forgetting is the worst this may do.
    return {}
  }
}

export function rememberedMapping(accountId: string): CsvMapping | undefined {
  return read()[accountId]
}

export function rememberMapping(accountId: string, mapping: CsvMapping): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...read(), [accountId]: mapping }))
  } catch {
    // Not worth telling anyone about: the import itself succeeded.
  }
}

/**
 * The remembered mapping, but only where it still fits this file. A bank that
 * renamed a column would otherwise pre-fill a field with a header the file
 * does not have, and the request would be refused for a reason the user did
 * not cause.
 */
export function applicableMapping(accountId: string, headers: string[]): CsvMapping | undefined {
  const remembered = rememberedMapping(accountId)
  if (!remembered) return undefined
  const present = new Set(headers)
  const usable = Object.fromEntries(
    Object.entries(remembered).filter(([, column]) => column && present.has(column))
  ) as CsvMapping
  return Object.keys(usable).length ? usable : undefined
}
