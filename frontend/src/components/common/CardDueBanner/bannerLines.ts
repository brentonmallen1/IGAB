import type { CardDueDismissal } from '../../../api/cardDueDismissals'
import {
  reminderForCard,
  type CardDueAccount,
  type CardDueLiability,
  type CardDueReminder,
} from '../../../utils/paymentDue'

/**
 * Whether this card's reminder is one somebody already dismissed. Exact on
 * date AND state: dismissing "due" does not hide the "past due" that may
 * follow for the same date, and one date's dismissal never silences the next.
 */
export function isDismissed(
  dismissals: CardDueDismissal[],
  accountId: string,
  reminder: CardDueReminder
): boolean {
  return dismissals.some(
    (d) =>
      d.account_id === accountId && d.due_date === reminder.dueDate && d.state === reminder.state
  )
}

/** One line of the banner: a card whose bill needs saying, not yet dismissed. */
export interface BannerLine {
  accountId: string
  name: string
  /** What the card owes now — the liability's owed-positive balance. */
  owed: number
  reminder: CardDueReminder
}

/**
 * Which cards the banner speaks about, in the order it says them.
 *
 * Pure composition: the reminder is `reminderForCard`'s answer — the one the
 * credit-cards strip and the terms header read too — and this only drops the
 * ones somebody dismissed and orders the rest. Past due first (it is already
 * late), then the soonest, then by name so the order is stable.
 */
export function bannerLines(
  liabilities: (CardDueLiability & { linked_account_id: string | null })[],
  accounts: (CardDueAccount & { id: string; name: string })[],
  dismissals: CardDueDismissal[],
  today: string
): BannerLine[] {
  const byId = new Map(accounts.map((a) => [a.id, a]))
  const lines: BannerLine[] = []
  for (const liability of liabilities) {
    const account = liability.linked_account_id ? byId.get(liability.linked_account_id) : undefined
    if (!account) continue
    const reminder = reminderForCard(liability, account, today)
    if (!reminder || isDismissed(dismissals, account.id, reminder)) continue
    lines.push({
      accountId: account.id,
      name: account.name,
      owed: liability.current_balance,
      reminder,
    })
  }
  const rank = (l: BannerLine) => (l.reminder.state === 'past_due' ? 0 : 1)
  return lines.sort(
    (a, b) => rank(a) - rank(b) || a.reminder.days - b.reminder.days || a.name.localeCompare(b.name)
  )
}
