/**
 * Has a person started an entry in the add editor?
 *
 * Describe and From receipt replace the manual form wholesale — a scan by
 * handing off to a review editor, a description by overwriting the fields —
 * so they are offered only while that would lose nothing: the rule Quick add
 * applies to its own Scan and Describe buttons. Typing a long split and then
 * tapping Scan used to throw the split away.
 *
 * `pristine` is the form as it stood before a person touched it. The
 * editor's own prefills (a budget-row category, its recent payee, an AI
 * draft) are that baseline, not an entry — so an AI draft can be described
 * again, which replaces only the AI's words.
 */
export interface EntryFields {
  date: string
  payeeQuery: string
  categoryId: string
  memo: string
  outflow: string
  inflow: string
}

export function entryStarted(
  current: EntryFields,
  pristine: EntryFields,
  mode: { isSplit: boolean; isTransfer: boolean }
): boolean {
  if (mode.isSplit || mode.isTransfer) return true
  return (Object.keys(current) as (keyof EntryFields)[]).some((k) => current[k] !== pristine[k])
}

/** What a tap on an inactive tab says — the reason, and what to do instead. */
export const STARTED_ENTRY_NOTE = {
  receipt:
    "A scan starts a new transaction and would replace what you've entered. Save this one, then attach the receipt to it.",
  describe:
    "Describing starts over and would replace what you've entered. Clear the form to describe it instead.",
} as const
