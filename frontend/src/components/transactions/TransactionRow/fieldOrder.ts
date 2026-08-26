import type { EditableField } from '../../../stores/transactionEditStore'

/**
 * Which register cell Tab moves to next — one rule for the row, pure so it
 * is testable without mounting it.
 *
 * The order is the row's left-to-right order. A cell that cannot be edited
 * on this row is skipped: the payee of a linked transfer is its
 * destination; a split parent's category lives on its lines; an
 * off-budget account has no categories at all. Tab past the last cell (or
 * Shift+Tab before the first) ends editing rather than wrapping — wrapping
 * onto the same row is how a user tabs in circles.
 */
export const FIELD_ORDER: readonly EditableField[] = [
  'date',
  'payee',
  'category',
  'memo',
  'outflow',
  'inflow',
]

export interface FieldContext {
  isTransfer: boolean
  isSplit: boolean
  onBudget: boolean
}

export function isFieldEditable(field: EditableField, ctx: FieldContext): boolean {
  switch (field) {
    case 'payee':
      return !ctx.isTransfer
    case 'category':
      return !ctx.isSplit && ctx.onBudget
    default:
      return true
  }
}

export function nextEditableField(
  from: EditableField,
  direction: 1 | -1,
  ctx: FieldContext
): EditableField | null {
  let i = FIELD_ORDER.indexOf(from) + direction
  while (i >= 0 && i < FIELD_ORDER.length) {
    if (isFieldEditable(FIELD_ORDER[i], ctx)) return FIELD_ORDER[i]
    i += direction
  }
  return null
}
