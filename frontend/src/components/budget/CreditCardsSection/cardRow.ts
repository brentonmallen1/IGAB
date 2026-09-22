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

/**
 * What the Set aside column PRINTS, which is never a negative.
 *
 * The figure itself stays signed everywhere else — the breakdown, the month
 * history and the server all keep it — because a card that went below zero in
 * March needs to say so. What the column cannot do is print `-$100.00` under
 * a one-word heading and leave the reader to guess which of four unrelated
 * situations produced it. The magnitude moves to a named line beside it
 * (`setAsideLabel`) and the explanation to a sentence under the row
 * (`stateSentence`), both visible without hovering anything.
 */
export function setAsideShown(card: CardStatus): number {
  return Math.max(0, card.set_aside)
}

/**
 * The short line beside the figure: how this card is unusual, in three words.
 *
 * Keyed on the served state and nothing else. The old note branched on causes
 * the client had guessed at — one of them comparing a LIFETIME residual
 * against a CURRENT shortfall — and spent one label, "ahead of budget", on
 * three situations with different remedies. Null on a card with nothing to
 * say, which is most of them.
 */
export function setAsideLabel(card: CardStatus, money: Money): string | null {
  switch (card.set_aside_state) {
    case 'funded':
      return null
    case 'surplus':
      return `${money(card.over_reserved)} spare`
    case 'card_holds_it':
      return 'credit balance'
    default:
      // The four below-zero states. No noun — they want opposite responses,
      // and one word for all four is what made this column unreadable. The
      // distance is a fact; the sentence under the row says what it means.
      return `${money(card.short_reserved)} below zero`
  }
}

export interface StateSentence {
  /** What is true, always. */
  sentence: string
  /** What to do about it — ABSENT wherever no action is honestly available.
   *  The affordance is what forced the old advice: a row that must end in a
   *  suggestion will invent one, and on a shared shortfall the one it
   *  invented moved a different card. */
  action?: string
}

/**
 * The card's situation in a sentence, and an action only where one is true.
 *
 * One entry per served state, no branching on a cause of its own. Every
 * figure quoted is a served leg, and which leg matters: on a settle-up the
 * sentence names `residual` — what actually came back — and never
 * `short_reserved`, which is only what was left of it after the month's
 * reservations and payments. A card whose envelope plainly shows $500 read
 * "$100 came back" for exactly that reason.
 */
export function stateSentence(card: CardStatus, money: Money): StateSentence | null {
  switch (card.set_aside_state) {
    case 'funded':
      return null

    case 'surplus':
      return {
        sentence:
          `${money(card.over_reserved)} more is set aside than this card owes. Money assigned ` +
          `to a card stays in its envelope until riding debt turns up to retire, so on a card ` +
          `you pay from funded envelopes it simply accumulates.`,
        action: 'Release it and it goes back to Ready to Assign, where it came from.',
      }

    case 'card_holds_it':
      return {
        sentence:
          `This card owes nothing and is holding ${money(card.card_credit)} of yours. Later ` +
          `spending on it, or a refund, will absorb the balance.`,
      }

    case 'settled_by_others':
      return {
        sentence:
          `${money(card.residual)} came back onto this card from spending nobody budgeted ` +
          `for — somebody settled up. It paid the card down by the same amount it took out ` +
          `of Set aside, and no envelope of yours lost anything.`,
        action: 'Nothing to do.',
      }

    case 'refund_outran_envelope':
      return {
        sentence:
          `${money(card.residual)} came back onto this card beyond anything an envelope ` +
          `charged here. An envelope is holding that money and you can spend it — but it ` +
          `never arrived in your bank. It exists as a credit on this card.`,
      }

    case 'settled_elsewhere':
      return {
        sentence:
          `${money(card.riding)} of spending rode onto this card when a month ended short, ` +
          `and that month's shortfall rode onto another card as well. Money put into the ` +
          `envelope is shared out across those cards, so it may not reach this one.`,
        action: `Assigning to this card is the only move that is certain to reach it.`,
      }

    case 'ride_unfunded':
      return {
        sentence:
          `${money(card.riding)} of spending rode onto this card when a month ended short, ` +
          `so your payment ran past what had been set aside.`,
        action:
          `Raise that month's assignment on the envelope and the ride is retired — the ` +
          `breakdown names the months. Or assign ${money(card.short_reserved)} to the card ` +
          `to cover it now.`,
      }

    case 'paid_ahead':
      return {
        sentence:
          `You have paid ${money(card.short_reserved)} more toward this card than any ` +
          `envelope set aside — it went straight to the balance.`,
        action:
          `Assign ${money(card.short_reserved)} to the card to settle up. Ready to Assign ` +
          `falls by that much, because the money has already left your account.`,
      }
  }
}

/**
 * A reserve whose identity does not close, as a visible sentence.
 *
 * Was a `title` attribute, which on an installed iOS PWA is unreachable — the
 * same half-finished migration the breakdown's legs were rescued from.
 */
export function driftSentence(card: CardStatus, money: Money): string | null {
  if (card.reserve_discrepancy === 0) return null
  return (
    `${money(card.reserve_discrepancy)} of this Set aside is not explained by assignments, ` +
    `payments or unclaimed rows. The integrity check has the detail.`
  )
}

/**
 * Which way the debt moved, in one word. The Balance cell's note and the
 * drawer's month total both say it, so they say it the same way.
 *
 * Never "up"/"down": the raw balance rises as the debt falls, so a bare
 * direction word gets read against the sign the reader is looking at — a
 * month that added $412 of debt said "down $412" beside a balance that had
 * grown. "increased"/"decreased" names the debt, which is the only quantity
 * this row is framed in. Zero counts as decreased, and callers that draw a
 * figure suppress it before asking.
 */
export function debtMovementWord(moved: number): 'increased' | 'decreased' {
  return moved >= 0 ? 'decreased' : 'increased'
}

/**
 * The Balance cell's note: how far the debt moved this month.
 *
 * Debt-framed on purpose. The raw balance rises as the debt falls, and showing
 * that unlabelled is the confusion this whole row is trying to end.
 *
 * A label and nothing else. It carried a `title` spelling out the month's
 * charges and payments, which the breakdown's "This month" block already
 * renders as rows — visibly, and on a phone at all.
 */
export function debtMovementLabel(card: CardStatus, money: Money): string | null {
  const moved = card.debt_change_this_month
  if (moved === 0) return null
  // A non-breaking space inside the phrase: the column is narrower than
  // "debt increased $412.00", so the note wraps — but only ever between the
  // phrase and the figure, never mid-phrase, which is the wrap that read as
  // a layout accident. "this month" is not in it: the page is already scoped
  // to one month and the longer phrasing wrapped mid-sentence.
  return `debt\u00A0${debtMovementWord(moved)} ${money(Math.abs(moved))}`
}

/**
 * Money that came onto the card this month and was not a payment from your
 * own accounts — a refund, a statement credit, someone else paying the bill,
 * or a payment recorded as a plain deposit instead of a transfer. Only a
 * transfer spends the card's reserve, so this is the term that leaves a card
 * reserving far more than it owes.
 *
 * A difference of two SERVED figures, never a plug: this used to be
 * reconstructed as `debt_change + charged − paid`, which cannot fail to
 * reconcile — any error in the other terms was silently absorbed and
 * relabelled "other credits". Now the server serves what arrived
 * (`inflows_this_month`, every credit) and what was paid
 * (`paid_this_month`, paired transfers only); the gap between the two is the
 * diagnostic, in `card_month_flows`' own words.
 */
export function otherCredits(card: CardStatus): number {
  const other = card.inflows_this_month - card.paid_this_month
  // Cents, not floats: a 1e-13 residue would draw a note about nothing.
  return Math.round(other * 100) / 100
}

export interface CardLeg {
  label: string
  value: number
  sign: '+' | '−'
}

/** The five terms a reserve is made of. */
export interface ReserveTerms {
  assigned: number
  reserved: number
  released: number
  residual: number
  payments: number
  /** An import anchor's B−1 seed (server: CardStatusOut.opening /
   *  CardTimelineMonthOut.opening). Zero everywhere but anchored budgets. */
  opening: number
}

/**
 * The legs a reserve is made of — which five, in what order, carrying which
 * sign — for a lifetime total or for one month.
 *
 * Both live in the same drawer: the list at the top is the card's lifetime
 * legs, and a month's row expands to the same five for that month. They are
 * one rule, so the set, the order and the signs are written once. Two copies
 * of a sign table is how a drawer comes to say a refund added to the reserve
 * in one place and subtracted from it in another.
 *
 * Zero legs are dropped: a month lists what moved, not what did not.
 */
export function reserveLegs(terms: ReserveTerms): CardLeg[] {
  return (
    [
      { label: 'Where YNAB left it at import', value: terms.opening, sign: '+' },
      { label: 'Assigned to this card', value: terms.assigned, sign: '+' },
      { label: 'Set aside by funded spending', value: terms.reserved, sign: '+' },
      { label: 'Released by refunds', value: terms.released, sign: '−' },
      { label: 'Refunds beyond what was reserved', value: terms.residual, sign: '−' },
      { label: 'Paid to the card', value: terms.payments, sign: '−' },
    ] satisfies CardLeg[]
  ).filter((leg) => leg.value !== 0)
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

/**
 * What to say about rows the bank still calls pending, or null when there are
 * none.
 *
 * `POSTED` keeps provisional rows out of every money aggregate, so the month
 * figures above and the balance beside them agree with each other — and both
 * differ from the register, which lists a pending row the moment the bank
 * mentions it. A user counting charges in the register found more than the
 * panel showed, with nothing on screen accounting for the difference.
 *
 * Per CLAUDE.md the divergence is fine and the silence is not: this names it
 * and the amount bounds it, so a gap that widens says so instead of
 * accumulating quietly. Deliberately NOT added to the figures above — a
 * pending amount is provisional and often arrives changed.
 */
export function pendingNote(card: CardStatus, money: Money): string | null {
  const pending = card.pending_this_month
  if (pending === 0) return null
  const kind = pending < 0 ? 'of charges' : 'of credits'
  return (
    `Posted rows only. ${money(Math.abs(pending))} ${kind} on this card ` +
    `is still pending, so the register shows more than this.`
  )
}
