import type { Transaction } from '../../types'

/**
 * What a register category cell shows, and what clicking it does — for a
 * transaction row and for the split lines drawn under one.
 *
 * Both lived inline in `TransactionRow`. The register's "show split lines"
 * view draws a category for every line and lets a click on a line open its
 * split, so it needed both answers too; copying them would have given the
 * lines their own idea of when a reconciled split opens the editor instead,
 * or what an uncategorized leg reads as. One module, both callers.
 */

export type CategoryCellLabel =
  | { kind: 'split' }
  | { kind: 'category'; name: string }
  /** The server's `needs_category`, never a rule rebuilt here. `was` is
   *  provenance from a category delete, not a category. */
  | { kind: 'needs-category'; was: string | null }
  /** No category and none needed on a budget account: internal money movement. */
  | { kind: 'transfer' }
  /** A tracking account: categories do not apply. */
  | { kind: 'untracked' }

export function categoryCellLabel(
  txn: Pick<Transaction, 'is_split' | 'category_id' | 'needs_category' | 'prior_category_name'>,
  categoryMap: ReadonlyMap<string, string>,
  accountOnBudget: boolean
): CategoryCellLabel {
  if (txn.is_split) return { kind: 'split' }
  if (txn.category_id) return { kind: 'category', name: categoryMap.get(txn.category_id) ?? '—' }
  if (txn.needs_category) return { kind: 'needs-category', was: txn.prior_category_name ?? null }
  return accountOnBudget ? { kind: 'transfer' } : { kind: 'untracked' }
}

/** What a click on the category cell opens. `split`: the inline split editor.
 *  `edit`: the full editor — a reconciled split's lines are still viewable and
 *  editable there, with the money locked. `category`: the inline picker. */
export type CategoryCellAction = 'split' | 'edit' | 'category' | null

export function categoryCellAction(
  txn: Pick<Transaction, 'is_split' | 'cleared'>,
  ctx: { isMobile: boolean; accountOnBudget: boolean }
): CategoryCellAction {
  // On a phone the whole row is one tap target that opens the editor; a
  // tracking account has no categories to pick.
  if (ctx.isMobile || !ctx.accountOnBudget) return null
  const reconciled = txn.cleared === 'reconciled'
  if (txn.is_split) return reconciled ? 'edit' : 'split'
  return reconciled ? null : 'category'
}
