import type { CardStatus } from '../../../types'

/**
 * What a card's row says about itself, decided once and away from the DOM.
 *
 * The strip used to print "overpaid" on the sign of `set_aside` alone, so a
 * card owing thousands wore the word while its owner paid the debt down. The
 * server now serves `card_position` (domain/cards.py) — `card_credit`,
 * `short_reserved`, `over_reserved` — and these read it. **Nothing here
 * re-derives a position from `set_aside` and `balance`;** that mirror is the
 * shape of the defect, not the fix.
 */

type Money = (n: number) => string

export interface RowNote {
  label: string
  title: string
}

/**
 * The note beside Ready to pay, for all three ways it can be worth explaining.
 *
 * The cause branches matter because the remedies differ. In order of how
 * completely each explains the number:
 *
 * 1. `card_credit` — the card owes nothing and holds money. The only state
 *    "overpaid" was ever true of, and it needs no action.
 * 2. `residual` alone covers the shortfall — money arrived on the card that no
 *    envelope had riding there. Someone else paying the bill, a refund for a
 *    purchase made before the budget started, or a payment onto this card for
 *    spending done on another.
 * 3. `riding` — a month ended short and the shortfall rode onto the card. The
 *    cheap remedy is back-funding THAT month, which nothing used to name.
 * 4. Otherwise a deliberate paydown: payment ran ahead of the assignment.
 */
export function reserveNote(card: CardStatus, money: Money): RowNote | null {
  if (card.card_credit > 0) {
    return {
      label: 'credit balance',
      title:
        `This card owes nothing and is holding ${money(card.card_credit)} of yours. ` +
        `Later spending on it, or a refund, will absorb the balance.`,
    }
  }

  if (card.short_reserved > 0) {
    const owed = money(card.short_reserved)
    if (card.residual >= card.short_reserved && card.residual > 0) {
      return {
        label: 'ahead of budget',
        title:
          `${money(card.residual)} has come back onto this card beyond anything an ` +
          `envelope charged to it — someone else paying the bill, a refund for a ` +
          `purchase made before this budget started, or a payment onto this card for ` +
          `spending done on another. It lowers the reserve without releasing any ` +
          `envelope's cash.`,
      }
    }
    if (card.riding > 0) {
      return {
        label: 'ahead of budget',
        title:
          `${money(card.riding)} of spending rode onto this card when a month ended ` +
          `short, so your payment ran past what was reserved. Fund that month's ` +
          `envelope and the ride disappears — or assign ${owed} to the card to cover ` +
          `it now.`,
      }
    }
    return {
      label: 'ahead of budget',
      title:
        `You have paid ${owed} more toward this card than any envelope set aside — it ` +
        `went straight to the balance. Assign ${owed} to the card to settle up: Ready ` +
        `to Assign falls by that much, because the money has already left your account.`,
    }
  }

  if (card.over_reserved > 0) {
    // Deliberately not keyed on `reserve_discrepancy`. That check's bounds are
    // allowances — an over-reserve explained by assignments satisfies T1 and
    // reports nothing — so a row keyed on it stays silent on exactly the card
    // that has drifted furthest. Show the distance and name what covers it.
    const spare = money(card.over_reserved)
    const byAssignment = card.assigned > 0 && card.riding === 0
    return {
      label: `${spare} spare`,
      title: byAssignment
        ? `${spare} more than this card owes. Money assigned to a card stays in its ` +
          `envelope until riding debt is there to retire, and this card has none — so ` +
          `assignments accumulate. Safe to release: type a negative in Assigned. That ` +
          `money did leave Ready to Assign when you assigned it, so releasing it hands ` +
          `back real spendable money.`
        : `${spare} more than this card owes — reserved cash the bill has not caught up ` +
          `with yet. Safe to release: type a negative in Assigned.`,
    }
  }

  return null
}

/**
 * The Balance cell's note: how far the debt moved this month.
 *
 * Debt-framed on purpose. The raw balance rises as the debt falls, and showing
 * that unlabelled is the confusion this whole row is trying to end.
 */
export function debtMovement(card: CardStatus, money: Money): RowNote | null {
  const moved = card.debt_change_this_month
  if (moved === 0) return null
  const charged = money(card.charged_this_month)
  const paid = money(card.paid_this_month)
  // "this month" lives in the tooltip, not the label: the Balance column is
  // barely wider than the figure above it, and the longer phrasing wrapped to
  // a second line mid-sentence. The page is already scoped to one month.
  const detail = `${charged} charged, ${paid} paid to the card this month.`
  return moved > 0
    ? { label: `down ${money(moved)}`, title: `${detail} The debt fell.` }
    : { label: `up ${money(-moved)}`, title: `${detail} The debt grew.` }
}

/**
 * Money that came onto the card this month and was not a payment from your own
 * accounts — a refund, a statement credit, someone else paying the bill, or a
 * payment recorded as a plain deposit instead of a transfer.
 *
 * The month block shows Charged, Paid and the net, and those three do not
 * reconcile when this is non-zero. Leaving that as a silent gap is the thing
 * worth avoiding: only a transfer spends the card's reserve, so a payment
 * typed as a deposit lowers the balance while Ready to pay stands still — the
 * exact shape that leaves a card reserving far more than it owes.
 *
 *     debt_change = paid + other − charged   ⇒   other = debt_change + charged − paid
 */
export function unexplainedInflow(card: CardStatus): number {
  const other = card.debt_change_this_month + card.charged_this_month - card.paid_this_month
  // Cents, not floats: a 1e-13 residue would draw a note about nothing.
  return Math.round(other * 100) / 100
}

export interface RideMonths {
  shown: CardStatus['rode_by_month']
  elided: number
  /** Gross total that ever rode, less what is still riding — money an
   *  assignment has already retired. Zero when nothing has been covered. */
  retired: number
}

/**
 * The months that put riding debt on this card, largest first, capped.
 *
 * Largest first because the list is capped and the copy tells the reader to
 * fund one of these months: eliding the biggest would point them at the
 * smallest win. `elided` is returned rather than dropped — a truncated list
 * that does not say it was truncated reads as the whole story.
 *
 * **`rode_by_month` is gross and `riding` is net**, so they disagree once an
 * assignment has retired part of the ride. There is no month attribution for
 * what remains: the walk records retirement against the month of the
 * assignment, not the month that rode. `retired` is that difference, and the
 * panel says it — otherwise the list points at months already settled.
 */
export function rideMonths(card: CardStatus, limit = 3): RideMonths {
  const all = [...card.rode_by_month].sort((a, b) => b.amount - a.amount)
  const gross = all.reduce((sum, m) => sum + m.amount, 0)
  return {
    shown: all.slice(0, limit),
    elided: Math.max(0, all.length - limit),
    retired: Math.max(0, Math.round((gross - card.riding) * 100) / 100),
  }
}

/**
 * What the legs list says when all five of them are zero.
 *
 * "Nothing has moved through this card yet" is true of a card nobody has used
 * and flatly false of a card carrying a balance whose spending was never filed
 * to an envelope — a card printed that line directly above "Charged
 * $2,400.00", contradicting itself inside one panel.
 *
 * The five legs are the **reserve**, not the card. A busy card reserves
 * nothing when its charges are uncategorized (nothing to set aside against)
 * and nothing has been assigned to it, which is exactly the state that reads
 * as the whole balance uncovered.
 */
export function emptyLegsNote(card: CardStatus): string {
  const untouched =
    card.balance === 0 && card.charged_this_month === 0 && card.debt_change_this_month === 0
  return untouched
    ? 'Nothing has moved through this card yet.'
    : 'Nothing has been set aside for this card yet — nothing assigned to it, and no spending on it filed to a funded envelope.'
}
