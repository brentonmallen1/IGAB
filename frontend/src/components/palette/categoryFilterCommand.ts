/**
 * `filter: rent` in the command palette, read as an instruction to narrow the
 * budget grid.
 *
 * The budget page already has a category filter — a text box in the filter
 * bar that writes `categorySearch` — and this adds a second way to reach it,
 * not a second implementation of it. Everything about *which* categories
 * match still lives in BudgetTable's needle; this decides only whether the
 * thing typed into the palette was a filter instruction and what term it
 * carried.
 *
 * Deliberately not part of the register's search vocabulary in
 * `searchParser.ts`. Those tokens (`category:`, `is:`, `amount:`) all select
 * transactions and mean the same thing in the palette as in the register's
 * own box. This one selects rows on a different page, so putting it in that
 * list would offer it in a box where it does nothing.
 */

export interface CategoryFilterCommand {
  /** The term to filter by; empty means "clear the filter". */
  term: string
}

//: `filter:` is the documented spelling; a bare space is accepted because it
//: is what people type, and `filters` is not — that would swallow a search
//: for a saved filter by name.
const FILTER_QUERY = /^filter\s*:\s*(.*)$|^filter\s+(.+)$/i

/**
 * The filter instruction in `query`, or null if it isn't one.
 *
 * Null for `filter` alone: a bare word is how someone searches for the saved
 * filters in the list below, and hijacking it would hide them behind a row
 * that filters by nothing.
 */
export function parseCategoryFilterCommand(query: string): CategoryFilterCommand | null {
  const match = FILTER_QUERY.exec(query.trim())
  if (!match) return null
  return { term: (match[1] ?? match[2] ?? '').trim() }
}

/** What the palette row says it will do. */
export function categoryFilterLabel(command: CategoryFilterCommand): string {
  return command.term ? `Filter categories: ${command.term}` : 'Clear the category filter'
}
