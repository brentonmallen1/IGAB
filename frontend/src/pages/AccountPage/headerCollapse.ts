/**
 * Whether the account header is folded away.
 *
 * The header carries the account's identity, its three balances, a pending
 * line, a bank-drift warning and five buttons. All of it earns its place when
 * you arrive at the account; almost none of it does while you are working
 * down the register reconciling, which is exactly when vertical space is
 * worth the most — every row the header occupies is a row of the statement
 * you cannot see.
 *
 * Derived rather than stored, which is what makes reconcile behave. A
 * reconcile collapses the header and finishing one restores whatever the
 * person had chosen, with no ref to remember the previous value and no
 * effect to put it back: the stored choice is never written by reconciling,
 * so it is still there when the derivation stops forcing the issue.
 *
 * Pure: three booleans in, one out. The component beside it owns the
 * measuring and the store.
 */

/**
 * @param stored  What the person last chose, or null if they never have.
 * @param isMobile  Phone width.
 * @param reconciling  A reconcile is in progress ON THIS ACCOUNT. The store's
 *   flag is global, so the caller must have already compared the account id —
 *   passing the bare flag would collapse every account's header at once.
 */
export function resolveHeaderCollapsed(
  stored: boolean | null,
  isMobile: boolean,
  reconciling: boolean
): boolean {
  // Reconciling wins over a stored choice, deliberately. Someone who likes
  // the header open still wants the rows while they are ticking off a
  // statement, and the toggle is right there when they disagree.
  if (reconciling) return true
  if (stored !== null) return stored
  // Never asked: a phone starts folded, because the full header left the
  // register one row tall on a 390pt screen. A desktop starts open.
  return isMobile
}
