import type { Transaction } from '../../types'
import {
  categoryDisplay,
  UNKNOWN_CATEGORY,
  type CategoryDisplay,
  type NamedCategory,
} from '../../utils/categoryLabels'

/**
 * What a register category cell shows, and what clicking it does — for a
 * transaction row and for the split lines drawn under one.
 *
 * Both lived inline in `TransactionRow`. The register's "show split lines"
 * view draws a category for every line and lets a click on a line open its
 * split, so it needed both answers too; copying them would have given the
 * lines their own idea of when a reconciled split opens the editor instead,
 * or what an uncategorized leg reads as. One module, both callers.
 *
 * Every other list that draws a transaction's category reads the label too:
 * the report drill-down, the merge preview and the late-arrivals note each
 * spelled their own, and each drew some row differently from the register —
 * see `categoryCell.test.ts`, where every divergence is a case named for the
 * component that had it.
 */

export type CategoryCellLabel =
  | { kind: 'split' }
  /** `path` is "Group › Category" for the hover: two envelopes can share a
   *  name in different groups. Null when the id cannot be named. */
  | ({ kind: 'category' } & CategoryDisplay)
  /** The server's `needs_category`, never a rule rebuilt here. `was` is
   *  provenance from a category delete, not a category. */
  | { kind: 'needs-category'; was: string | null }
  /** No category and none needed on a budget account: internal money movement. */
  | { kind: 'transfer' }
  /** A tracking account: categories do not apply. */
  | { kind: 'untracked' }

export function categoryCellLabel(
  txn: Pick<Transaction, 'is_split' | 'category_id' | 'needs_category' | 'prior_category_name'>,
  labels: ReadonlyMap<string, NamedCategory>,
  accountOnBudget: boolean
): CategoryCellLabel {
  if (txn.is_split) return { kind: 'split' }
  if (txn.category_id) return { kind: 'category', ...categoryDisplay(txn.category_id, labels) }
  if (txn.needs_category) return { kind: 'needs-category', was: txn.prior_category_name ?? null }
  return accountOnBudget ? { kind: 'transfer' } : { kind: 'untracked' }
}

/** The label as plain text, for a list that draws it without the register's
 *  chip and chevron. The register says "Split Transaction" with a chevron;
 *  in plain text a split is "Split". */
export function categoryCellText(label: CategoryCellLabel): string {
  switch (label.kind) {
    case 'split':
      return 'Split'
    case 'category':
      return label.name
    case 'needs-category':
      return 'Needs Category'
    case 'transfer':
      return 'Transfer'
    case 'untracked':
      return UNKNOWN_CATEGORY
  }
}

/** The hover for a category cell: the path when the row is filed in a
 *  category the labels can name, nothing otherwise. */
export function categoryCellHover(label: CategoryCellLabel): string | null {
  return label.kind === 'category' ? label.path : null
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
