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

/** How a card's Set aside pill is coloured: red is overspent, green is
 *  money waiting, grey is nothing either way. The same three a spending
 *  envelope's Available uses, so a card reads like any envelope. */
export type PillTone = 'negative' | 'positive' | 'zero'

/** Why a card's line carries a dot: it needs you. */
export type LineMark = 'overspent' | 'to-file' | 'not-covered'

/** Most urgent first: the order `cardLine` checks them in, and the order the
 *  section header picks its one dot from. */
const MARK_SEVERITY: readonly LineMark[] = ['overspent', 'to-file', 'not-covered']

/** What the header's dot says to a screen reader, which cannot see its colour. */
const MARK_LABEL: Record<LineMark, string> = {
  overspent: 'A card is overspent',
  'to-file': 'A card has transactions to categorize',
  'not-covered': 'A card owes more than is set aside',
}

/**
 * Whether what a card owes beyond its Set aside is a warning. It is: paying
 * past Set aside is overspending (red, and next month's Ready to Assign
 * covers it), so "not covered" is the step before red. It read as calm grey
 * once, and a card whose red had only moved — a funded charge refilling a
 * hole a payment dug — looked settled. The line and the opened card's figure
 * both ask this.
 */
export function notCoveredWarns(card: Pick<CardStatus, 'uncovered'>): boolean {
  return card.uncovered > 0
}

/**
 * The section header's one dot: the most urgent any card's line carries, so
 * a folded list still says there is something inside to look at. Null when
 * no line has a dot.
 */
export function sectionMark(lines: Pick<CardLine, 'mark'>[]): {
  mark: LineMark
  label: string
} | null {
  const mark = MARK_SEVERITY.find((m) => lines.some((l) => l.mark === m))
  return mark ? { mark, label: MARK_LABEL[mark] } : null
}

export interface CardLine {
  /** One or two words after the name — what the card is doing, at a glance. */
  word: string
  /** Set only when there is something to act on this month. */
  mark: LineMark | null
  tone: PillTone
  /** 0..1: how much of what the card owes is covered by Set aside — the
   *  filled part of the line's bar. Nothing owed reads as fully covered. */
  covered: number
}

/**
 * What a card's one line says, before anyone opens it.
 *
 * The line is read, not studied: a word, a bar and the Set aside pill, with
 * a dot only where the card needs you this month. Everything here is
 * composition of served figures — `set_aside`, `uncovered`, `over_reserved`,
 * `card_credit` and the account's `uncategorized_count` — and decides no
 * money. The order is the order of urgency (`MARK_SEVERITY`): overspent first
 * (it reaches Ready to Assign on the 1st), then rows waiting for a category
 * (they decide what Set aside even is), then debt not covered (a payment
 * would turn it red), then the calm positions.
 */
export function cardLine(
  card: Pick<CardStatus, 'set_aside' | 'balance' | 'uncovered' | 'over_reserved' | 'card_credit'>,
  toCategorize: number,
  money: Money
): CardLine {
  const owed = Math.max(0, -card.balance)
  const covered = owed === 0 ? 1 : Math.min(1, Math.max(0, card.set_aside) / owed)
  const tone: PillTone = card.set_aside < 0 ? 'negative' : card.set_aside > 0 ? 'positive' : 'zero'
  if (card.set_aside < 0) return { word: 'overspent', mark: 'overspent', tone, covered }
  if (toCategorize > 0) {
    return {
      word: toCategorize === 1 ? '1 to categorize' : `${toCategorize} to categorize`,
      mark: 'to-file',
      tone,
      covered,
    }
  }
  if (card.card_credit > 0) {
    return { word: `holds ${money(card.card_credit)} of yours`, mark: null, tone, covered }
  }
  if (notCoveredWarns(card)) {
    return { word: `${money(card.uncovered)} not covered`, mark: 'not-covered', tone, covered }
  }
  if (card.over_reserved > 0) {
    return { word: `${money(card.over_reserved)} spare`, mark: null, tone, covered }
  }
  if (owed === 0) return { word: 'paid off', mark: null, tone, covered }
  return { word: 'covered', mark: null, tone, covered }
}

/**
 * What an opened card says about itself: at most one callout.
 *
 * It was a paragraph per state — the situation, why, and every remedy, in
 * two or three sentences — stacked with more paragraphs for rows to file and
 * rides. Nobody read it. Now: a headline a glance can take ("Overspent by
 * $100.00"), one short line of cause, and the fix as a button. Calm
 * positions get no callout at all; the Owes / Covered / Not covered figures
 * above it already say everything true about them.
 *
 * One entry per served state and no cause of its own. Every figure is a
 * served leg: on a settle-up the line names `residual_from_ledgers_this_month`
 * — what actually came back — never `short_reserved`, which is only what is
 * left of it after the month's reservations and payments.
 */
export interface Callout {
  tone: 'overspent' | 'calm'
  headline: string
  /** One short line: why. Never a remedy — that is the button. */
  reason: string
  /** Assigning this much to the card this month squares it. Absent where
   *  nothing needs doing: a row that must end in a suggestion invents one. */
  assign: number | null
  /** Under the button, or alone when there is none: what happens if nothing
   *  is done, or the other way out. */
  otherwise: string | null
}

/** What a red card turns into if it is left alone. */
const LEFT_ALONE = 'Otherwise it comes out of next month\u2019s Ready to Assign on the 1st.'

export function cardCallout(card: CardStatus, money: Money): Callout | null {
  const short = card.short_reserved
  const overspent = (reason: string, otherwise = LEFT_ALONE): Callout => ({
    tone: 'overspent',
    headline: `Overspent by ${money(short)}`,
    reason,
    assign: short,
    otherwise,
  })
  switch (card.set_aside_state) {
    case 'funded':
      return null

    case 'surplus':
      return {
        tone: 'calm',
        headline: `${money(card.over_reserved)} spare`,
        reason: 'Assigned to the card, but no debt has needed it.',
        assign: null,
        otherwise: 'Keep it for the next bill, or release it to Ready to Assign.',
      }

    case 'card_holds_it':
      // Paid past the balance, the card's envelope went below zero too.
      if (short > 0) {
        return overspent(
          `Paid past the balance: the card holds ${money(card.card_credit)} of yours.`
        )
      }
      return {
        tone: 'calm',
        headline: `Holds ${money(card.card_credit)} of yours`,
        reason: 'You paid it more than it owed. Later spending on it uses that up.',
        assign: null,
        otherwise: null,
      }

    case 'settled_by_others':
      // Nothing to fix: somebody else paid the card down by exactly what it
      // took from Set aside. Red, and no button.
      return {
        ...overspent(
          `Somebody settled up ${money(card.residual_from_ledgers_this_month)} on this card.`,
          'Nothing to do. The 1st covers it from Ready to Assign, and the card owes that much less.'
        ),
        assign: null,
      }

    case 'refund_outran_envelope':
      return overspent(
        `${money(card.residual_this_month - card.residual_from_ledgers_this_month)} came back ` +
          'to an envelope that never charged this card.'
      )

    case 'settled_elsewhere':
      return overspent(
        `A short month\u2019s ${money(card.riding)} rode onto this card and another.`
      )

    case 'ride_unfunded':
      return overspent(
        `A short month put ${money(card.riding)} on this card, and your payment ran past it.`,
        'Or raise that month\u2019s envelope. ' + LEFT_ALONE
      )

    case 'paid_ahead':
      return overspent('Your payment ran past what was set aside.')

    case 'moved_out':
      return overspent('More was moved out of its envelope than it held.')

    case 'mixed':
      // Name what is present; split nothing. The reserve identity is bounds,
      // not parts, so "how much is which" has no honest answer here.
      return overspent('More than one thing took from it. The breakdown has each.')
  }
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
 * consequence is stated rather than enforced — past the spare, what is not
 * covered rises dollar for dollar, which is a deliberate choice to carry more of this
 * card's balance.
 *
 * Two served anchors and no third figure. "Not covered after this" would need
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
          `Past ${money(spare)}, every dollar you take out is a dollar of this card's debt not ` +
            `covered. That is allowed: it means choosing to carry more of the balance.`,
        ]
      : [
          `${money(held)} is set aside for this card's bill, and none of it is spare.`,
          `Every dollar you take out is a dollar of this card's debt not covered. That is ` +
            `allowed: it means choosing to carry more of the balance.`,
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
 * Which way the debt moved, in one word — the breakdown's month total.
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

/** The terms a reserve is made of. */
export interface ReserveTerms {
  assigned: number
  reserved: number
  released: number
  residual: number
  payments: number
  /** An import anchor's B−1 seed (server: CardStatusOut.opening /
   *  CardTimelineMonthOut.opening). Zero everywhere but anchored budgets. */
  opening: number
  /** Overspending covered from Ready to Assign on a 1st (server:
   *  CardStatusOut.written_off / CardTimelineMonthOut.written_off). */
  written_off: number
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
      { label: 'Covered from Ready to Assign on the 1st', value: terms.written_off, sign: '+' },
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
