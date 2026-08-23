/**
 * The judgement calls in the YNAB mapping step, kept out of the page so they
 * can be tested directly.
 *
 * The mapping step is where a real 47-account import went wrong: four assets
 * were given debt types, which subtracted ~$2.8M from net worth and spawned
 * four phantom liabilities. The suggester had them right and flagged all four
 * for review — nothing objected when the user overrode it. So this module is
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

/** How far a balance must sit on the wrong side of its type before we say so.
 *
 *  Not zero: a credit card paid in full often rests slightly positive, and a
 *  warning on every paid-off card is one people learn to ignore — which would
 *  cost us the warning that matters. $1,000 stays quiet there while still
 *  catching both real cases, the $1.2M house typed as a mortgage and the
 *  $6,111 overpaid auto loan. */
export const SIGN_MISMATCH_FLOOR = 1000

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
 * Does the chosen type disagree with the balance's sign?
 *
 * Warns, never blocks. An overpaid loan is real — `Vehicle A Loan` genuinely
 * held +$6,111 — so this has to be a remark the user can walk past, not a
 * gate. Returns the sentence to show, or null.
 */
export function balanceWarning(
  classification: 'asset' | 'liability' | undefined,
  balance: number
): string | null {
  if (classification === 'liability' && balance > SIGN_MISMATCH_FLOOR) {
    return "This is a debt type, but the balance is positive — that usually means something you own. If it really is an overpaid debt, carry on."
  }
  if (classification === 'asset' && balance < -SIGN_MISMATCH_FLOOR) {
    return 'This is an asset type, but the balance is negative — that usually means something you owe.'
  }
  return null
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
