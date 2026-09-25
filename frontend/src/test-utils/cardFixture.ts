import type { CardStatus } from '../types'

/**
 * Refuse a card fixture the server could never serve.
 *
 * `uncovered`, `over_reserved`, `short_reserved` and `card_credit` are the
 * four terms of one position, decided in one place (`domain/cards.py`
 * `card_position`) from `set_aside` and `balance` — and the components read
 * the served terms independently and trust them. That is correct for real
 * data and a trap for fixtures: six test cards typed `uncovered: 0` beside a
 * Set aside below zero, or a `surplus` position labelled `funded`, and every
 * test passed because nothing compared the fields to each other. A server
 * change to `card_position` would have surfaced nowhere here.
 *
 * This is the same arithmetic as `card_position`, in test code, held to the
 * server by the served-row scenario suite — the one copy a differential test
 * is allowed. Call it from every card factory. It throws, so the fixture is
 * fixed at the point it was written rather than silently believed.
 */
/**
 * The four position terms from `set_aside` and `balance` — what the server
 * would serve for them. Use it in a card factory so a fixture cannot state a
 * position its own two inputs contradict; the label is still the writer's,
 * and `assertServerProducible` checks it where the position decides it.
 */
export function withPosition<T extends Pick<CardStatus, 'set_aside' | 'balance'>>(
  card: T
): T & Pick<CardStatus, 'uncovered' | 'over_reserved' | 'short_reserved' | 'card_credit'> {
  const owed = -card.balance
  return {
    ...card,
    uncovered: Math.max(0, owed - Math.max(0, card.set_aside)),
    over_reserved: Math.max(0, card.set_aside - Math.max(0, owed)),
    short_reserved: Math.max(0, -card.set_aside),
    card_credit: Math.max(0, -owed),
  }
}

export function assertServerProducible(card: CardStatus): CardStatus {
  const owed = -card.balance
  const want = {
    uncovered: Math.max(0, owed - Math.max(0, card.set_aside)),
    over_reserved: Math.max(0, card.set_aside - Math.max(0, owed)),
    short_reserved: Math.max(0, -card.set_aside),
    card_credit: Math.max(0, -owed),
  }
  const wrong = (Object.keys(want) as (keyof typeof want)[]).filter(
    (k) => Math.abs(card[k] - want[k]) > 0.005
  )
  if (wrong.length) {
    throw new Error(
      `card fixture "${card.name}" is not one the server would serve: ` +
        wrong.map((k) => `${k}=${card[k]} (position says ${want[k]})`).join(', ') +
        ` — from set_aside=${card.set_aside}, balance=${card.balance}`
    )
  }
  // The label the server would put on it, for the states this can decide
  // from the position alone. The below-zero states need legs it cannot see.
  if (card.card_credit > 0 && card.set_aside_state !== 'card_holds_it') {
    throw new Error(
      `card fixture "${card.name}" holds a credit but is labelled ${card.set_aside_state}`
    )
  }
  if (card.card_credit === 0 && card.short_reserved === 0) {
    const want = card.over_reserved > 0 ? 'surplus' : 'funded'
    if (card.set_aside_state !== want) {
      throw new Error(
        `card fixture "${card.name}" is labelled ${card.set_aside_state}; its position says ${want}`
      )
    }
  }
  return card
}

/**
 * A served card row, built from a neutral default — a funded card with nothing
 * on it — plus the fields a test cares about. The four position terms are
 * derived (`withPosition`) and the result is checked (`assertServerProducible`).
 *
 * One builder, because six test files each carried their own full copy of
 * every field, so renaming one served field broke all six at once and a new
 * field had to be added six times.
 */
export function cardStatus(over: Partial<CardStatus> = {}): CardStatus {
  return assertServerProducible(
    withPosition({
      account_id: 'a1',
      name: 'Sapphire Visa',
      category_id: 'c1',
      balance: 0,
      set_aside: 0,
      uncovered: 0,
      is_closed: false,
      overspent_this_month: 0,
      reserve_discrepancy: 0,
      assigned: 0,
      reserved: 0,
      released: 0,
      residual: 0,
      payments: 0,
      opening: 0,
      written_off: 0,
      written_off_this_month: 0,
      riding: 0,
      imported_riding: 0,
      covered: 0,
      residual_this_month: 0,
      residual_from_ledgers_this_month: 0,
      ride_reaches_this_card: true,
      over_reserved: 0,
      short_reserved: 0,
      card_credit: 0,
      set_aside_state: 'funded',
      charged_this_month: 0,
      inflows_this_month: 0,
      paid_this_month: 0,
      debt_change_this_month: 0,
      pending_this_month: 0,
      rode_by_month: [],
      overspent_by_category: [],
      ...over,
    })
  )
}
