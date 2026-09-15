import type { SavingsMode, SavingsRole } from '../types'

/**
 * How a savings category's money counts as saved — the words for each choice,
 * written once.
 *
 * Read by the category inspector's radio (`SavingsModeField`) and by the
 * compact per-row control in a tag's checklist (`CategoryMembershipList`), so
 * the two directions of choosing say the same thing. Presentation only: which
 * mode a category has is the server's `savings_role`.
 */
export interface SavingsModeOption {
  mode: SavingsMode
  /** The inspector's sentence end: "Counts as saved when money is: …". */
  label: string
  /** Short enough for one checklist row. */
  short: string
  consequence: string
}

export const SAVINGS_MODE_OPTIONS: readonly SavingsModeOption[] = [
  {
    mode: 'sent_out',
    label: 'sent out of this envelope',
    short: 'sent out',
    consequence: 'Spending or transfers from here count as saved; assigning doesn’t.',
  },
  {
    mode: 'kept_here',
    label: 'kept in this envelope',
    short: 'kept here',
    consequence: 'What this envelope holds is saved; spending from it lowers your savings.',
  },
]

/** The marker beside the choice the tags would make with nothing stored. */
export const DEFAULT_MARKER = '(default)'

export function savingsModeShort(mode: SavingsRole): string | null {
  return SAVINGS_MODE_OPTIONS.find((o) => o.mode === mode)?.short ?? null
}
