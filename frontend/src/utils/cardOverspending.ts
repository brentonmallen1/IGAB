/**
 * A card's Set aside below zero, in words — said the same way everywhere.
 *
 * A negative Set aside is overspending on the card's envelope, and like any
 * overspent envelope it is covered from Ready to Assign on the 1st unless it
 * is squared before then. The card strip ends every below-zero state with
 * this sentence and the payment dialog warns with it, so it lives once.
 */

/** How every below-zero card sentence ends. */
export function thisMonthOrNext(amount: string): string {
  return `Assign ${amount} to the card this month, or it comes out of next month’s Ready to Assign.`
}

/**
 * How far below zero a payment would leave a card's Set aside, or null when
 * it would not. A payment is the reserve's `payments` leg — it lowers Set
 * aside by exactly its amount (domain/cards.py `CardReserve`) — so this is
 * that subtraction on the served `set_aside`, and decides nothing the walk
 * does not.
 */
export function overspentAfterPayment(setAside: number, amount: number): number | null {
  const after = Math.round((setAside - amount) * 100) / 100
  return after < 0 ? -after : null
}
