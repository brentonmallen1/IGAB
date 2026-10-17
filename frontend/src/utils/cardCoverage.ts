/**
 * What a card owes, and how much of that its Set aside covers.
 *
 * Three places asked and each spelled it: the strip's collapsed line (its
 * bar), the opened card's Owes / Covered figures, and the payment dialog's
 * "pay what is set aside" prefill — the same `min(owed, max(0, set_aside))`
 * three times, in two features. Here once, so the bar, the figure under it
 * and the amount the dialog proposes cannot disagree about one card.
 *
 * Pure presentation of served figures, so it stays on the client (CLAUDE.md's
 * boundary rule): no backend path decides it. **Not** the served
 * `CardStatus.covered`, which is a different quantity entirely — what
 * assignments have retired of riding debt, lifetime.
 *
 * `balance` is the card's ledger, negative when owed: the budget month's card
 * row through the viewed month on the strip, the account's live balance in
 * the payment dialog. Each caller says which; the arithmetic is the same.
 */
export interface CardCoverage {
  /** What the card owes; zero for a card paid off or in credit. */
  owed: number
  /** How much of `owed` Set aside stands behind: never more than owed, never
   *  below zero. */
  covered: number
  /** `covered / owed`, 0..1 — the filled part of the strip's bar. Nothing
   *  owed reads as fully covered. */
  share: number
}

export function cardCoverage(card: { balance: number; set_aside: number }): CardCoverage {
  const owed = Math.max(0, -card.balance)
  const covered = Math.min(owed, Math.max(0, card.set_aside))
  return { owed, covered, share: owed === 0 ? 1 : covered / owed }
}
