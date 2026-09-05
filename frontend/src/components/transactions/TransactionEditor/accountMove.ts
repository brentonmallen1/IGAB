/**
 * What the editor's Account field may do on a row that already exists.
 *
 * The rule itself lives on the server — `backend/src/igab/domain/account_move.py`
 * refuses a move it must refuse, whatever any client believes. This module
 * decides only whether to *offer* the control, and what to say instead when it
 * does not: an editor that shows an enabled picker for a bank-fed row teaches
 * the user to expect a move and then hands them a 400.
 *
 * So the two copies answer different questions and cannot silently disagree
 * about money: the worst a stale copy here can do is offer a control the
 * server then declines, in its own words.
 *
 * Kept pure (facts in, string out) so every branch is a one-line test.
 */

import { rowMayCarryCategory } from '../../../utils/rowCategoryRule'

export interface AccountLockFacts {
  /** The statement vouched for a balance in one account. */
  isReconciled: boolean
  /** The row came from a bank feed (`sync_id`), which owns which account it
   *  lives in — the feed is account-scoped and would re-add it. */
  isBankFed: boolean
  /** A split's line. Its account is the parent's; the parent is the editable
   *  row, and moving it takes the lines along. */
  isSplitLine: boolean
}

/**
 * Why this row's account cannot be changed here, or null when it can.
 *
 * The sentence is shown beside the field, so it says what to do next rather
 * than only what is forbidden.
 */
export function accountLockReason(facts: AccountLockFacts): string | null {
  if (facts.isSplitLine) {
    return 'Split lines live in the same account as the transaction they belong to.'
  }
  if (facts.isReconciled) {
    return 'Reconciled — a statement vouched for this account. Unlock from the row menu to move it.'
  }
  if (facts.isBankFed) {
    return 'Your bank feed decides which account this one lives in. Delete it and enter it by hand to put it elsewhere.'
  }
  return null
}

/**
 * The note under the picker when the account the row is heading for cannot
 * hold the category it currently has. Saving clears it — say so before the
 * save, not after.
 *
 * Asks `rowMayCarryCategory` rather than re-spelling it: this is the same
 * rule the field's visibility already uses, pointed at the target account.
 */
export function categoryDropNote(
  targetOnBudget: boolean,
  categoryName: string | null
): string | null {
  if (rowMayCarryCategory(targetOnBudget) || !categoryName) return null
  return `Tracking accounts don't carry categories — ${categoryName} will be cleared.`
}
