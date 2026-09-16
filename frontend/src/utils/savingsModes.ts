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
  /** The inspector's sentence end: "Counts as saved: …". */
  label: string
  /** Short enough for one checklist row. */
  short: string
  consequence: string
}

export const SAVINGS_MODE_OPTIONS: readonly SavingsModeOption[] = [
  {
    mode: 'kept_here',
    label: 'while it’s in the budget',
    short: 'in budget',
    consequence:
      'What this envelope holds is saved, whichever on-budget account the money sits in; spending from it lowers your savings.',
  },
  {
    mode: 'sent_out',
    label: 'when it leaves the budget',
    short: 'leaves budget',
    consequence:
      'Anything that leaves this envelope counts as saved — a transfer to an off-budget account or a payment anywhere IGAB doesn’t track; assigning doesn’t.',
  },
]

/** What "in the budget" and "leaving the budget" mean, for any place that
 *  defines the two choices rather than just offering them. */
export const SAVINGS_MODES_DEFINITION =
  'In the budget means money held in your on-budget accounts; leaving the budget means moving it to an off-budget account or paying it somewhere IGAB doesn’t track.'

/** The marker beside the choice the tags would make with nothing stored. */
export const DEFAULT_MARKER = '(default)'

export function savingsModeShort(mode: SavingsRole): string | null {
  return SAVINGS_MODE_OPTIONS.find((o) => o.mode === mode)?.short ?? null
}

/** The full words, for prose: "counts as saved when it leaves the budget". */
export function savingsModeLabel(mode: SavingsMode): string {
  const option = SAVINGS_MODE_OPTIONS.find((o) => o.mode === mode)
  if (!option) throw new Error(`No savings mode ${mode}`)
  return option.label
}
