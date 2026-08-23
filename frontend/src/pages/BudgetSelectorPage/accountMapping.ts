/**
 * The judgement calls in the YNAB mapping step, kept out of the page so they
 * can be tested directly.
 *
 * The mapping step is where a real 47-account import went wrong: four assets
 * were given debt types, which subtracted ~$2.8M from net worth and spawned
 * four phantom liabilities. The suggester had all four right and flagged them
 * for review — nothing objected when they were overridden. So this module is
 * about *confirmation*, not guessing.
 */
import type { YnabAccountPreview, YnabAccountTypeChoice } from '../../api/budgets'
import { monthsAgoStartISO } from '../../utils/dateWindow'

/** What happens to an account at import time. */
export type Disposition = 'import' | 'close' | 'skip'

/** Months without a transaction before an account reads as dormant. A year
 *  clears seasonal accounts (an annual insurance payment, a holiday fund)
 *  while still catching the 2019–2021 group in a real export. */
export const DORMANT_AFTER_MONTHS = 12

export function dispositionOf(choice: YnabAccountTypeChoice | undefined): Disposition {
  if (choice?.skip) return 'skip'
  if (choice?.close) return 'close'
  return 'import'
}

/** Both flags are always written, so switching away from a disposition clears
 *  the one it set. Leaving `close` behind on a row switched back to `import`
 *  would close an account the user just said to keep open. */
export function choiceForDisposition(d: Disposition): Pick<YnabAccountTypeChoice, 'skip' | 'close'> {
  return { skip: d === 'skip', close: d === 'close' }
}

export function isDormant(lastActivity: string | null, monthsAgoISO?: string): boolean {
  if (!lastActivity) return false
  return lastActivity < (monthsAgoISO ?? monthsAgoStartISO(DORMANT_AFTER_MONTHS))
}

/** "Mar 2019" — a month is the right precision for "when did this last move". */
export function activityLabel(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

/**
 * Does the chosen type disagree with what the account looks like?
 *
 * Keyed on disagreement with the *suggestion*, deliberately not on the sign of
 * `implied_balance`. That figure is the sum of the register, and a YNAB export
 * contains no account balance and no starting-balance row — so on a
 * date-filtered export it is the sum of a *window*, not a balance. Measured on
 * a real 47-account export beginning 01/01/2019: a sign test fires on ten
 * correctly-typed accounts, among them a checking account summing to -$14,335
 * and a savings to -$9,603, because the money that opened them predates the
 * export. Ten false alarms out of forty-seven is how a warning becomes
 * something people click past — and then the one that matters goes past too.
 *
 * Disagreement with the suggestion has none of that noise: it fires only when
 * someone actively overrides the classification, which is rare and worth a
 * glance. It still catches every case that went wrong for real — all four
 * mistyped assets were suggested `other_asset`.
 *
 * Warns, never blocks. An overpaid loan is real, and so is a name we read
 * wrongly. Returns the sentence to show, or null.
 */
export function classificationWarning(
  suggested: 'asset' | 'liability' | undefined,
  chosen: 'asset' | 'liability' | undefined
): string | null {
  if (!suggested || !chosen || suggested === chosen) return null
  if (chosen === 'liability') {
    return 'A debt type, but this reads as something you own. Worth checking the balance — an asset filed as a debt is subtracted from net worth instead of added, and arrives with a payoff record it does not need.'
  }
  return 'An asset type, but this reads as something you owe. Worth checking the balance — a debt filed as an asset is added to net worth instead of subtracted.'
}

/** Accounts that would arrive dormant-but-open, i.e. the ones worth offering
 *  "import & close". Used for the summary line above the list. */
export function dormantOpenCount(
  accounts: YnabAccountPreview[],
  choices: Record<string, YnabAccountTypeChoice>,
  monthsAgoISO?: string
): number {
  return accounts.filter(
    (a) => dispositionOf(choices[a.name]) === 'import' && isDormant(a.last_activity, monthsAgoISO)
  ).length
}

/** A run of consecutive rows sharing a related-account label. */
export interface AccountSection {
  label: string | null
  accounts: YnabAccountPreview[]
}

/**
 * Split the preview into captioned runs.
 *
 * Runs rather than buckets, so the list stays in the backend's alphabetical
 * order and a caption appears where a family starts. Bucketing would hoist
 * every ungrouped account to wherever the first one happened to fall, which
 * makes a 47-row list harder to scan, not easier.
 */
export function groupAccounts(accounts: YnabAccountPreview[]): AccountSection[] {
  const sections: AccountSection[] = []
  for (const a of accounts) {
    const label = a.related_group ?? null
    const last = sections[sections.length - 1]
    if (last && last.label === label) {
      last.accounts.push(a)
    } else {
      sections.push({ label, accounts: [a] })
    }
  }
  return sections
}
