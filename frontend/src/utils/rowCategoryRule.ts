/**
 * May this transaction row carry a category?
 *
 * The client half of the rule whose one server home is
 * `backend/src/igab/domain/transfers.py` (`leg_may_carry_category`): a
 * category may sit only on an ON-BUDGET row — off-budget activity is
 * net-worth movement, not budget spending — and on a transfer leg, only when
 * the partner is off-budget. The server refuses what this hides; this exists
 * so the editors never offer what the save would refuse.
 *
 * Irreducible duplication, one implementation per side: every category field
 * the client renders (register row, full editor, quick add) reads this and
 * nothing else.
 */
export function rowMayCarryCategory(
  onBudget: boolean,
  partnerOnBudget: boolean | null = null
): boolean {
  if (partnerOnBudget === null) return onBudget
  return onBudget && !partnerOnBudget
}
