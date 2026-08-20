// Pure account/liability grouping for the sidebar (and accounts overview).
// Kept free of React so the money math and "nothing may vanish" rules are
// unit-testable: every account must land in exactly one section, and every
// liability must render exactly once.

import type { Account } from '../../../types'
import { BUILTIN_ACCOUNT_TYPES } from '../../../constants/accountTypes'

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
 * - managed liabilities whose linked account isn't in that set (an on-budget
 *   or closed linked account previously made the liability render nowhere)
 * - unmanaged (manually tracked) liabilities
 */
export function buildLiabilityRows(
  offBudgetLiabilityAccounts: Account[],
  liabilities: LiabilitySummary[]
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

export function assetsTotal(offBudgetAssets: Account[]): number {
  return offBudgetAssets.reduce((sum, a) => sum + Number(a.balance), 0)
}
