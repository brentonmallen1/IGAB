// Pure account/liability grouping for the sidebar (and accounts overview).
// Kept free of React so the money math and "nothing may vanish" rules are
// unit-testable: every account must land in exactly one section, and every
// liability must render exactly once.

import type { Account } from '../../../types'
import { BUILTIN_ACCOUNT_TYPES, accountTypeLabel } from '../../../constants/accountTypes'

/** The collapsible groups the sidebar draws, by the id their collapsed state
 * is stored under. Here rather than spelled out at the toggle and again at the
 * `.has()` — a section whose header writes one id and whose body reads another
 * is a group that never collapses, and nothing would fail loudly. */
export const SIDEBAR_SECTION_IDS = {
  budgetAccounts: 'budget-accounts',
  assets: 'assets',
  liabilities: 'liabilities',
} as const

export function sidebarTypeGroupId(typeKey: string): string {
  return `type:${typeKey}`
}

/** The slice of a Liability these helpers need */
export interface LiabilitySummary {
  id: string
  name: string
  linked_account_id: string | null
  current_balance: number
}

export interface AccountPartition {
  onBudgetByType: Map<string, Account[]>
  offBudgetAssets: Account[]
  offBudgetLiabilityAccounts: Account[]
}

export function partitionAccounts(accounts: Account[]): AccountPartition {
  const onBudgetByType = new Map<string, Account[]>()
  const offBudgetAssets: Account[] = []
  const offBudgetLiabilityAccounts: Account[] = []
  for (const acc of accounts) {
    if (acc.on_budget) {
      const list = onBudgetByType.get(acc.account_type)
      if (list) list.push(acc)
      else onBudgetByType.set(acc.account_type, [acc])
    } else if (acc.classification === 'liability') {
      offBudgetLiabilityAccounts.push(acc)
    } else {
      // Defensive: classification is always derived post-migration, but a
      // stray NULL must land somewhere visible rather than vanish.
      offBudgetAssets.push(acc)
    }
  }
  return { onBudgetByType, offBudgetAssets, offBudgetLiabilityAccounts }
}

const BUILTIN_ORDER = BUILTIN_ACCOUNT_TYPES.map((t) => t.key)

/** Type keys whose label already names a set. "Checkings" is not a word. */
const UNCOUNTABLE_TYPES = new Set(['checking', 'cash', 'savings', 'tracking'])

/** A group header names a set of accounts, so it pluralizes the type label.
 * The wording itself always comes from `accountTypeLabel`: the sidebar used to
 * carry its own switch over every built-in key, which meant renaming a type in
 * the registry left the header saying the old name and nothing failed. */
export function groupLabel(typeKey: string, registry?: { key: string; label: string }[]): string {
  const label = accountTypeLabel(typeKey, registry)
  if (UNCOUNTABLE_TYPES.has(typeKey) || label.endsWith('s')) return label
  // Consonant + y takes -ies. "Other Liability" is the one built-in that needs
  // it, and a custom type is far likelier to want it than "Liabilitys".
  if (/[^aeiou]y$/i.test(label)) return `${label.slice(0, -1)}ies`
  return `${label}s`
}

/** On-budget type keys present, built-ins in canonical order first, then
 * custom keys alphabetically — custom-typed accounts always render. */
export function orderedOnBudgetKeys(onBudgetByType: Map<string, Account[]>): string[] {
  return [...onBudgetByType.keys()].sort((a, b) => {
    const ia = BUILTIN_ORDER.indexOf(a)
    const ib = BUILTIN_ORDER.indexOf(b)
    return (
      (ia === -1 ? BUILTIN_ORDER.length : ia) - (ib === -1 ? BUILTIN_ORDER.length : ib) ||
      a.localeCompare(b)
    )
  })
}

export interface LiabilityRow {
  key: string
  name: string
  /** Signed display amount: negative = owed */
  balance: number
  target: { kind: 'account'; accountId: string } | { kind: 'liability'; liabilityId: string }
  /** Managed rows keep a shortcut to the underlying account register */
  registerAccountId: string | null
  icon: 'managed' | 'manual' | null
}

/** Every debt, exactly once:
 * - off-budget liability-classified accounts — showing their Liability
 *   tracker's balance when linked, so an empty ledger doesn't read as $0 owed
 * - managed liabilities whose linked account is not rendered anywhere else
 *   (a closed linked account previously made the liability render nowhere)
 * - unmanaged (manually tracked) liabilities
 *
 * `onBudgetAccountIds` is what keeps the count at "once". Every
 * liability-classified account now carries a companion Liability, credit cards
 * included, and an on-budget card already has a row of its own in the
 * on-budget section — so its companion must not add a second one here, or the
 * same debt appears twice and the header total double-counts it.
 */
export function buildLiabilityRows(
  offBudgetLiabilityAccounts: Account[],
  liabilities: LiabilitySummary[],
  onBudgetAccountIds: ReadonlySet<string> = new Set()
): LiabilityRow[] {
  const rows: LiabilityRow[] = []
  const seenLiabilityIds = new Set<string>()

  for (const acc of offBudgetLiabilityAccounts) {
    const tracker = liabilities.find((l) => l.linked_account_id === acc.id)
    if (tracker) seenLiabilityIds.add(tracker.id)
    rows.push({
      key: `acct-${acc.id}`,
      name: acc.name,
      balance: tracker ? -Number(tracker.current_balance) : Number(acc.balance),
      target: tracker
        ? { kind: 'liability', liabilityId: tracker.id }
        : { kind: 'account', accountId: acc.id },
      registerAccountId: tracker ? acc.id : null,
      icon: tracker ? 'managed' : null,
    })
  }

  for (const liability of liabilities) {
    if (seenLiabilityIds.has(liability.id)) continue
    if (liability.linked_account_id && onBudgetAccountIds.has(liability.linked_account_id)) continue
    rows.push({
      key: `liab-${liability.id}`,
      name: liability.name,
      balance: -Number(liability.current_balance),
      target: { kind: 'liability', liabilityId: liability.id },
      registerAccountId: null,
      icon: liability.linked_account_id ? 'managed' : 'manual',
    })
  }
  return rows
}

/** The Liabilities header total: the sum of exactly what the section shows.
 * The old computation summed liability-classified account ledgers plus
 * unmanaged balances — a managed mortgage on an on-budget or classification-
 * less account contributed nothing, reading "$0.00 with nothing listed". */
export function liabilityHeaderTotal(rows: LiabilityRow[]): number {
  return rows.reduce((sum, r) => sum + r.balance, 0)
}

/** The one place account ledgers are summed — the on-budget header, the
 * Assets header, and every type-group subtotal all come through here. Three
 * hand-written copies of this reduce is how a header stops agreeing with the
 * rows beneath it. */
export function accountsTotal(accounts: Account[]): number {
  return accounts.reduce((sum, a) => sum + Number(a.balance), 0)
}

/** The Budget Accounts header total: the sum of exactly the group subtotals
 * listed beneath it, so collapsing a group never makes the arithmetic stop
 * adding up on screen. */
export function groupedAccountsTotal(onBudgetByType: Map<string, Account[]>): number {
  let sum = 0
  for (const list of onBudgetByType.values()) sum += accountsTotal(list)
  return sum
}
