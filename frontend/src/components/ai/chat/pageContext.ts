/**
 * What the user is looking at, derived from the route.
 *
 * Pure: a function of the pathname plus a little app state, with no `window`
 * and no hooks, so all seventeen branches are one-line tests. The alternative —
 * every page handing the chat a sentence about itself — is seventeen places to
 * forget, and seventeen wordings to drift.
 *
 * **The client sends structure; the server writes the sentence.** Which page
 * someone is on is a fact only the browser has, so it supplies it. Turning that
 * into prompt text is not presentational composition, so it does not live here:
 * a rendered string on the wire would have two homes the moment the server
 * wanted to word it differently. The Python side mirrors this union and rejects
 * a `kind` it does not know.
 */

export type PageContext =
  | { kind: 'budget'; month: string; selected_category_names?: string[] }
  | { kind: 'account'; account_name?: string }
  | { kind: 'reports'; tab: string }
  | {
      kind:
        | 'accounts'
        | 'transactions'
        | 'liabilities'
        | 'liability'
        | 'assets'
        | 'asset'
        | 'guide'
        | 'wishlist'
        | 'scheduled'
        | 'payees'
        | 'settings'
        | 'ai-activity'
        | 'activity'
        | 'import'
    }

export interface PageContextInputs {
  pathname: string
  /** The month the budget grid is showing, as YYYY-MM-DD. */
  selectedMonth?: string
  /** Envelopes the user has selected on the budget page, by name. */
  selectedCategoryNames?: string[]
  /** Which report is open. */
  reportTab?: string
  /** The account whose register is open. */
  accountName?: string
}

/** Routes whose identity is the whole context, keyed by their path. */
const SIMPLE: Record<string, PageContext['kind']> = {
  '/accounts': 'accounts',
  '/transactions': 'transactions',
  '/liabilities': 'liabilities',
  '/assets': 'assets',
  '/guide': 'guide',
  '/wishlist': 'wishlist',
  '/scheduled': 'scheduled',
  '/payees': 'payees',
  '/settings': 'settings',
  '/ai-activity': 'ai-activity',
  '/activity': 'activity',
  '/import': 'import',
}

/**
 * The typed context for a route, or null when there is nothing worth saying.
 *
 * Null rather than a guess: telling the model the user is somewhere they are
 * not is worse than telling it nothing.
 */
export function describePage(inputs: PageContextInputs): PageContext | null {
  const path = normalize(inputs.pathname)

  if (path === '/budget') {
    return {
      kind: 'budget',
      month: inputs.selectedMonth ?? '',
      // Only when there is a selection: an empty array would read to the
      // server as "they have selected nothing", which is a different claim.
      ...(inputs.selectedCategoryNames?.length
        ? { selected_category_names: inputs.selectedCategoryNames.slice(0, 20) }
        : {}),
    }
  }

  if (path === '/reports') {
    return { kind: 'reports', tab: inputs.reportTab ?? 'overview' }
  }

  // Detail routes carry an id we deliberately do not send. The server would
  // have to trust it, and the tools are budget-scoped from the request anyway.
  if (path.startsWith('/accounts/')) {
    return { kind: 'account', ...(inputs.accountName ? { account_name: inputs.accountName } : {}) }
  }
  if (path.startsWith('/liabilities/')) return { kind: 'liability' }
  if (path.startsWith('/assets/')) return { kind: 'asset' }

  const simple = SIMPLE[path]
  return simple ? ({ kind: simple } as PageContext) : null
}

/** Trailing slashes and query strings are not part of a route's identity. */
function normalize(pathname: string): string {
  const withoutQuery = pathname.split('?')[0].split('#')[0]
  if (withoutQuery.length > 1 && withoutQuery.endsWith('/')) {
    return withoutQuery.slice(0, -1)
  }
  return withoutQuery
}
