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

/**
 * Whether an account's balance is showing trouble or just showing a number.
 *
 * A negative balance means two different things depending on what the account
 * is. On a chequing or savings account it means overdrawn — something to act
 * on. On a credit card or a mortgage it means what is owed, which is the
 * normal state of a debt and not news. Colouring both the same is what made
 * the sidebar read as five alarms on an ordinary Tuesday, and it is the same
 * judgement the cards strip already makes about Uncovered.
 */
export type BalanceTone = 'neutral' | 'negative'

export function balanceTone(balance: number, kind: 'asset' | 'debt'): BalanceTone {
  return kind === 'asset' && balance < 0 ? 'negative' : 'neutral'
}

/** Which of the two an account is. A credit card is on-budget and a debt. */
export function accountKind(account: Pick<Account, 'classification'>): 'asset' | 'debt' {
  return account.classification === 'liability' ? 'debt' : 'asset'
}

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

/** Where a sidebar row sends you. Shared by account rows, liability rows and
 *  asset rows so the active-row rule below has one shape to reason about. */
export type SidebarRowTarget =
  | { kind: 'account'; accountId: string }
  | { kind: 'liability'; liabilityId: string }
  | { kind: 'asset'; assetId: string }

export interface LiabilityRow {
  key: string
  name: string
  /** Signed display amount: negative = owed */
  balance: number
  target: SidebarRowTarget
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
      balance: tracker ? -tracker.current_balance : acc.balance,
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
      balance: -liability.current_balance,
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

export interface AssetRow {
  key: string
  name: string
  balance: number
  target: SidebarRowTarget
  /** Stated (manually valued) rows carry the pen icon, like unmanaged debts. */
  icon: 'manual' | null
}

interface ValuedAssetLike {
  id: string
  name: string
  current_value: number | null
}

/** Every asset, exactly once — the Debts rule mirrored:
 * - off-budget asset-classified accounts (brokerage, an HSA), from their
 *   ledgers
 * - valued Assets (a home, a vehicle), from their stated values; one with no
 *   value point yet still gets a row at 0, because a thing being tracked and
 *   contributing nothing is a state worth seeing
 *
 * A valued Asset is never an account, so "once" is structural here; the same
 * real-world house existing as BOTH is the double-count the hygiene panel
 * suspects by name, not something this list can dedupe.
 */
export function buildAssetRows(
  offBudgetAssetAccounts: Account[],
  assets: ValuedAssetLike[]
): AssetRow[] {
  const rows: AssetRow[] = offBudgetAssetAccounts.map((acc) => ({
    key: `acct-${acc.id}`,
    name: acc.name,
    balance: acc.balance,
    target: { kind: 'account', accountId: acc.id },
    icon: null,
  }))
  for (const asset of assets) {
    rows.push({
      key: `asset-${asset.id}`,
      name: asset.name,
      balance: asset.current_value ?? 0,
      target: { kind: 'asset', assetId: asset.id },
      icon: 'manual',
    })
  }
  return rows
}

/** The header is the sum of what's listed — the same discipline as Debts. */
export function assetHeaderTotal(rows: AssetRow[]): number {
  return rows.reduce((sum, r) => sum + r.balance, 0)
}

/** The one place account ledgers are summed — the on-budget header, the
 * Assets header, and every type-group subtotal all come through here. Three
 * hand-written copies of this reduce is how a header stops agreeing with the
 * rows beneath it. */
export function accountsTotal(accounts: Account[]): number {
  return accounts.reduce((sum, a) => sum + a.balance, 0)
}

/** The Budget Accounts header total: the sum of exactly the group subtotals
 * listed beneath it, so collapsing a group never makes the arithmetic stop
 * adding up on screen. */
/**
 * The on-budget section's money, told apart.
 *
 * A credit card is on budget — its spending comes out of envelopes — but its
 * balance is not money you have. Summing the section flat produced cash minus
 * card debt, which answers neither "what have I got" nor "what do I owe", and
 * it is not the partition the budget itself uses: since cards left Ready to
 * Assign, `AccountRepository.sum_on_budget_balance` counts cash accounts only.
 * This is that same line, drawn once, on the side that renders headers.
 *
 * `net` is what the section header has always shown and still shows; `cash`
 * is the figure the sidebar had no way to say.
 */
export interface OnBudgetTotals {
  cash: number
  cards: number
  net: number
}

export function onBudgetTotals(onBudgetByType: Map<string, Account[]>): OnBudgetTotals {
  let cash = 0
  let cards = 0
  for (const list of onBudgetByType.values()) {
    for (const account of list) {
      const amount = account.balance
      if (accountKind(account) === 'debt') cards += amount
      else cash += amount
    }
  }
  return { cash, cards, net: cash + cards }
}

/**
 * Which account or liability the URL says you are looking at.
 *
 * Read from the path rather than from `appStore`, which used to hold a
 * `selectedAccountId` written on every sidebar click and read by nothing. That
 * field could only ever be right when the sidebar itself did the navigating,
 * so a deep link, a browser Back, or a jump from ⌘K all left it stale. The
 * path is the one thing that is true however you arrived.
 *
 * Pure, so every branch is a one-line test: the component side does no more
 * than hand it `location.pathname`.
 */
export type SidebarLocation =
  | { kind: 'account'; id: string }
  | { kind: 'liability'; id: string }
  | { kind: 'asset'; id: string }
  | null

export function parseSidebarLocation(pathname: string): SidebarLocation {
  const segments = pathname.split('/').filter(Boolean)
  // Exactly two: `/accounts` is the overview, and it highlights no row.
  if (segments.length !== 2) return null
  const [section, raw] = segments
  const id = decodeURIComponent(raw)
  if (section === 'accounts') return { kind: 'account', id }
  if (section === 'liabilities') return { kind: 'liability', id }
  if (section === 'assets') return { kind: 'asset', id }
  return null
}

/**
 * Whether a row is the one currently open.
 *
 * One rule for every row the sidebar draws — on-budget accounts, assets,
 * liabilities and the collapsed mini rail — because a managed liability is
 * reachable two ways and both must light the same row: its own liability page,
 * and the account register its shortcut button opens. Written per section, the
 * liability row would have been the copy that forgot the register.
 */
export function isRowActive(
  target: SidebarRowTarget,
  registerAccountId: string | null,
  location: SidebarLocation
): boolean {
  if (location === null) return false
  if (location.kind === 'liability') {
    return target.kind === 'liability' && target.liabilityId === location.id
  }
  if (location.kind === 'asset') {
    return target.kind === 'asset' && target.assetId === location.id
  }
  if (target.kind === 'account' && target.accountId === location.id) return true
  return registerAccountId !== null && registerAccountId === location.id
}

/** The row target for an ordinary account row. */
export function accountTarget(accountId: string): SidebarRowTarget {
  return { kind: 'account', accountId }
}
