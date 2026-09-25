import type { CardStatus } from '../../../types'
import type { DueNotice } from '../../../utils/paymentDue'

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
export function setAsideShown(card: Pick<CardStatus, 'set_aside'>): number {
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
      // The below-zero states. No noun — they want opposite responses, and
      // one word for all of them is what made this column unreadable. The
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
/** How every below-zero state ends: a negative Set aside is overspending on
 *  the card's envelope, and like any overspent envelope it is covered from
 *  Ready to Assign on the 1st unless it is squared before then. */
function thisMonthOrNext(amount: string): string {
  return `Assign ${amount} to the card this month, or it comes out of next month\u2019s Ready to Assign.`
}

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
        // This month's ledger residual, the figure the state was decided on —
        // not lifetime `residual`, which read "$4,000 came back … somebody
        // settled up" about a $150 settle-up.
        sentence:
          `${money(card.residual_from_ledgers_this_month)} came back onto this card from ` +
          `spending nobody budgeted for — somebody settled up. It paid the card down by the ` +
          `same amount it took out of Set aside.`,
        action:
          'Nothing to change. If Set aside is still below zero at the end of the month, next ' +
          'month\u2019s Ready to Assign covers it.',
      }

    case 'refund_outran_envelope':
      return {
        // This month's residual that is NOT a settle-up: what an envelope kept.
        sentence:
          `${money(card.residual_this_month - card.residual_from_ledgers_this_month)} came ` +
          `back onto this card beyond anything an envelope charged here. The envelope it was ` +
          `filed to is holding that money.`,
        action: thisMonthOrNext(money(card.short_reserved)),
      }

    case 'settled_elsewhere':
      return {
        sentence:
          `${money(card.riding)} of spending rode onto this card when a month ended short, ` +
          `and that month's shortfall rode onto another card as well. Money put into the ` +
          `envelope is shared out across those cards, so it may not reach this one.`,
        action:
          `Assigning to this card is the only move certain to reach it. ` +
          thisMonthOrNext(money(card.short_reserved)),
      }

    case 'ride_unfunded':
      return {
        sentence:
          `${money(card.riding)} of spending rode onto this card when a month ended short, ` +
          `so your payment ran past what had been set aside.`,
        action:
          `Raise that month's assignment on the envelope and the ride is retired — the ` +
          `breakdown names the months. Or: ` +
          thisMonthOrNext(money(card.short_reserved)),
      }

    case 'paid_ahead':
      return {
        sentence:
          `You have paid ${money(card.short_reserved)} more toward this card than any ` +
          `envelope set aside — it went straight to the balance.`,
        action: thisMonthOrNext(money(card.short_reserved)),
      }

    case 'moved_out':
      return {
        sentence:
          `${money(card.short_reserved)} more was moved out of this card's envelope than it ` +
          `held. No payment happened and nothing came back onto the card — the money is in ` +
          `Ready to Assign, or wherever it was moved, and the envelope is overdrawn.`,
        action: thisMonthOrNext(money(card.short_reserved)),
      }

    case 'mixed': {
      // Name what is present; quote each served leg; split nothing. The
      // reserve identity is bounds, not parts, so "how much of the shortfall
      // is which" is a question this row cannot answer honestly — and the
      // one-label model answered it anyway, calling a two-thirds settle-up
      // "you have paid $300 ahead". The legs panel is the whole picture.
      const parts: string[] = []
      if (card.residual_from_ledgers_this_month > 0) {
        parts.push(
          `${money(card.residual_from_ledgers_this_month)} came back from somebody settling up`
        )
      }
      const kept = card.residual_this_month - card.residual_from_ledgers_this_month
      if (kept > 0) parts.push(`${money(kept)} came back as a refund an envelope is holding`)
      if (card.riding > 0) parts.push(`${money(card.riding)} rode here when a month ended short`)
      parts.push('payments ran past what was set aside')
      return {
        sentence:
          `More than one thing is going on: ${joinList(parts)}. None of them accounts for the ` +
          `whole ${money(card.short_reserved)}, and this row will not guess the split.`,
        action: 'The breakdown has each figure. ' + thisMonthOrNext(money(card.short_reserved)),
      }
    }
  }
}

/** "a, b and c" — the list shape a sentence reads naturally. */
function joinList(parts: string[]): string {
  if (parts.length <= 1) return parts.join('')
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
}

export interface ReleaseAnchors {
  /** What the form starts at: the surplus, where there is one. */
  prefill: number
  /** Everything this card is holding — the most that can come out before the
   *  figure itself goes below zero. */
  ceiling: number
  /** The two lines under the amount box, in order. */
  lines: string[]
}

/**
 * What releasing money from a card costs, at each of the two anchors.
 *
 * Offered on ANY card holding money, not only one with a surplus. Set aside is
 * money committed to a bill, but committing it is a decision and so is
 * un-committing it: needing that cash for something else this month is a real
 * situation, and the app's job is to say what it does, not to refuse it. The
 * consequence is stated rather than enforced — past the spare, Uncovered
 * rises dollar for dollar, which is a deliberate choice to carry more of this
 * card's balance.
 *
 * Two served anchors and no third figure. "Uncovered after this" would need
 * either a preview endpoint or a second copy of `card_position` on the client,
 * and a client-side second opinion about a card's position is the defect this
 * whole section exists to end.
 */
export function releaseAnchors(card: CardStatus, money: Money): ReleaseAnchors {
  const spare = card.over_reserved
  const held = Math.max(0, card.set_aside)
  const lines =
    spare > 0
      ? [
          `${money(spare)} is spare — more than this card owes. Releasing up to that leaves ` +
            `the card exactly as covered as it is now.`,
          `Past ${money(spare)}, Uncovered rises by every dollar you take out. That is allowed: ` +
            `it means choosing to carry more of this balance.`,
        ]
      : [
          `${money(held)} is set aside for this card's bill, and none of it is spare.`,
          `Uncovered rises by every dollar you take out. That is allowed: it means choosing ` +
            `to carry more of this balance.`,
        ]
  // Prefill the spare, or nothing: prefilling `held` proposed emptying an
  // envelope that was exactly covering its bill. `ceiling` is what the form
  // refuses to exceed — below zero there is no money, only a deficit that
  // used to read as "you have paid ahead".
  return { prefill: spare > 0 ? spare : 0, ceiling: held, lines }
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
 * assignment, not the month that rode. `retired` is the served `covered` leg,
 * and the panel says it — otherwise the list points at months already
 * settled. It used to be reconstructed here as `gross − riding`, which was
 * wrong two ways at once: inflows that discharge a ride also lower `riding`
 * without any assignment, and on an imported budget `riding` carried the
 * opening debt that `rode_by_month` never had — so the difference went
 * negative, clamped to zero, and a real retirement was hidden.
 */
export function rideMonths(card: CardStatus, limit = 3): RideMonths {
  const all = [...card.rode_by_month].sort((a, b) => b.amount - a.amount)
  return {
    shown: all.slice(0, limit),
    elided: Math.max(0, all.length - limit),
    retired: card.covered,
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

export interface CardDue {
  name: string
  notice: DueNotice
}

/**
 * What the section's header says about bills falling due, or null when none
 * are close.
 *
 * The header is the only thing on screen when the strip is collapsed, and a
 * bill you cannot see coming is the one that catches you. It already carries
 * the section's other aggregate — what is uncovered across every card — and
 * this is the same shape: one line about all of them.
 *
 * Names the card when there is exactly one, because "which card" is the
 * question a strip with several of them raises, and a header with no answer
 * to it sends the reader to open the section to find out. With more than one
 * the count leads and the soonest sets the urgency; the rows carry the rest.
 */
export function dueHeaderNote(due: CardDue[]): string | null {
  if (due.length === 0) return null
  const soonest = due.reduce((a, b) => (b.notice.days < a.notice.days ? b : a))
  if (due.length === 1) return `${soonest.name} due ${soonest.notice.phrase}`
  return `${due.length} bills due, soonest ${soonest.notice.phrase}`
}
