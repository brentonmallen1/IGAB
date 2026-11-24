/**
 * The picking half of a merge, pure: what a click on one of the two cards
 * asks the server for next.
 *
 * It decides nothing about the result. Which fields are a choice, and which
 * row each value currently comes from, arrive on the preview
 * (`MergePreview.choices`); these only turn "the person clicked this" into
 * the next `keep` to ask with.
 */
import type { MergeChoice, MergeField, MergeKeep, MergePreview, Transaction } from '../../../types'
import { hasBankRecord } from '../../../utils/bankRecord'

/** Is this row's value part of the result for `field`? */
export function isKept(choice: MergeChoice, rowId: string): boolean {
  return choice.source === rowId || choice.source === 'both'
}

/**
 * A click on a card's value for a field the preview says is a choice.
 *
 * Date, payee and category are one-or-the-other: the clicked row's wins.
 * A memo is each-or-both — two different memos are joined by default, so a
 * click takes that row's memo out, or puts it back; the last one in cannot
 * be taken out, because a merge never drops a value the person did not ask
 * to drop for something else.
 */
export function pick(
  keep: MergeKeep,
  field: MergeField,
  choice: MergeChoice,
  rowId: string,
  otherId: string
): MergeKeep {
  if (!choice.choosable) return keep
  if (field !== 'memo') return { ...keep, [field]: rowId }
  if (choice.source === 'both') return { ...keep, memo: otherId }
  if (choice.source === rowId) return keep
  return { ...keep, memo: 'both' }
}

/** "Use all of this one": every field that is a choice, from this row. */
export function pickAll(keep: MergeKeep, preview: MergePreview, rowId: string): MergeKeep {
  const next: MergeKeep = { ...keep }
  for (const field of ['date', 'payee', 'category', 'memo'] as const) {
    if (preview.choices[field].choosable) next[field] = rowId
  }
  return next
}

/** Is anything about this merge the person's to choose? */
export function hasChoices(preview: MergePreview): boolean {
  return Object.values(preview.choices).some((c) => c.choosable)
}

/** Does this row already supply every field that is a choice? */
export function suppliesAll(preview: MergePreview, rowId: string): boolean {
  return Object.values(preview.choices)
    .filter((c) => c.choosable)
    .every((c) => c.source === rowId)
}

/**
 * What to call the two cards. A bank row and a hand-entered one — the usual
 * duplicate — are named for where they came from; two of a kind are told
 * apart by position, because their dates and amounts are usually identical.
 */
export function pairLabels(
  a: Pick<Transaction, 'has_sync_source' | 'sync_source'>,
  b: Pick<Transaction, 'has_sync_source' | 'sync_source'>
): [string, string] {
  const name = (t: typeof a) => (hasBankRecord(t) ? 'From the bank' : 'Entered by hand')
  const [first, second] = [name(a), name(b)]
  return first === second ? ['First transaction', 'Second transaction'] : [first, second]
}
