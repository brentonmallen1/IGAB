import type { AIJob, AIJobDraft, AIJobDraftCheck } from '../../api/aiJobs'
import { parseApiDecimal, toCents } from '../../utils/money'
import type { NamedCategory } from '../../utils/categoryLabels'

/**
 * Does the model's category label name this category?
 *
 * The label (`result.draft.category`, and each `suggested_split` line) is
 * the server's `category_matching.canonical_label`: the category's real
 * name, qualified as "Name (Group)" only when that name repeats. The server
 * already matched the model's words to a category; this only reads the
 * format back. `shared/category_label_cases.json` runs the writer and this
 * reader over the same cases.
 *
 * Case-insensitive, as the server's matcher is: a category renamed only in
 * case since the scan still reads as the one the model picked.
 */
export function labelNamesCategory(label: string, category: NamedCategory): boolean {
  const folded = label.toLowerCase()
  if (folded === category.name.toLowerCase()) return true
  return category.group !== null && folded === `${category.name} (${category.group})`.toLowerCase()
}

/**
 * The first of `categories` a label names, for turning a suggested split line
 * into a picker value. Undefined when none does (renamed or archived since),
 * which leaves that line's picker empty for the user to fill.
 */
export function categoryForLabel<C extends { id: string }>(
  label: string,
  categories: C[],
  labels: ReadonlyMap<string, NamedCategory>
): C | undefined {
  return categories.find((c) => {
    const named = labels.get(c.id)
    return named !== undefined && labelNamesCategory(label, named)
  })
}

/**
 * The model's category when the row is filed somewhere else, for "AI
 * suggested X" beside the category the row is in. Null when the model named
 * none, or named the category the row is in. `filed` is null for a row with
 * no category, where any pick the model made is a suggestion not taken.
 */
export function aiSuggestedCategory(
  draft: AIJobDraft | undefined,
  filed: NamedCategory | null
): string | null {
  const suggested = draft?.category
  if (!suggested) return null
  return filed && labelNamesCategory(suggested, filed) ? null : suggested
}

/**
 * The sentence for a category the model named and the budget could not
 * resolve. Shown wherever the model's reason is, because the reason names
 * that category: beside an uncategorized row with no note, it read as the AI
 * having filed the receipt somewhere else (reported 2026-09-24).
 */
export function unresolvedCategoryNote(draft: AIJobDraft | undefined): string | null {
  const named = draft?.category_unresolved
  if (!named) return null
  return `Suggested “${named}”, which isn’t exactly one of your categories, so it’s left uncategorized.`
}

/** What the receipt's card ending says about the account a scan sits in:
 *  - `switched` — the scan was submitted against another account and the
 *    worker moved it here, to the account the card is on file for. A record,
 *    so it is said after approval too;
 *  - `elsewhere` — the card that paid is on file for a different account;
 *  - `unknown` — the receipt printed an ending nobody has on file, so the
 *    review offers to remember it for this account.
 *  Null when the receipt showed no card, the scan has no account yet, or the
 *  ending is this account's own. Which account owns an ending is served
 *  (`card_ending_account_id`); this only compares served ids. */
export type CardEndingNote =
  | { kind: 'switched'; last4: string; fromId: string; hereId: string }
  | { kind: 'elsewhere'; last4: string; ownerId: string; hereId: string }
  | { kind: 'unknown'; last4: string; hereId: string }

export function cardEndingNote(job: AIJob): CardEndingNote | null {
  const last4 = job.result?.draft?.card_last4
  const hereId = job.transaction_account_id
  if (!last4 || !hereId) return null
  // Only while the row is still where the switch put it: moved back by hand,
  // the row is somewhere the card is not, and `elsewhere` says so.
  const switched = job.result?.account_switched
  if (switched && switched.to_account_id === hereId) {
    return { kind: 'switched', last4, fromId: switched.from_account_id, hereId }
  }
  const ownerId = job.card_ending_account_id
  if (!ownerId) return { kind: 'unknown', last4, hereId }
  if (ownerId !== hereId) return { kind: 'elsewhere', last4, ownerId, hereId }
  return null
}

/** The editor's formatters, passed in so this stays pure. */
interface CheckFormatters {
  formatDate: (iso: string) => string
  formatMoney: (amount: number) => string
}

/**
 * One sentence per field the read failed a check on, naming what was read
 * so the person knows what to look at. The checks are the server's
 * (`domain/receipt_checks.py`); this only words them. Empty when the read
 * passed, or predates the checks.
 */
export function draftCheckNotes(
  draft: AIJobDraft | undefined,
  { formatDate, formatMoney }: CheckFormatters
): string[] {
  const checks = draft?.checks ?? []
  if (!draft || checks.length === 0) return []
  const money = (value: string) => formatMoney(Math.abs(parseApiDecimal(value)))
  const notes: string[] = []
  if (checks.includes('date')) {
    notes.push(
      draft.date_read
        ? `The date read as ${formatDate(draft.date_read)}, too far from today, so it’s set to today — check it.`
        : 'The date didn’t look right, so it’s set to today — check it.'
    )
  }
  if (checks.includes('amount')) {
    const total = money(draft.amount)
    if (draft.tender_amount) {
      notes.push(
        `The total read as ${total}, but the payment line says ${money(draft.tender_amount)} — check the amount.`
      )
    }
    if (draft.line_items_total) {
      notes.push(
        `The items add up to ${money(draft.line_items_total)}, not the total ${total} — check the amount.`
      )
    }
    if (!draft.tender_amount && !draft.line_items_total) {
      notes.push('The total doesn’t match the rest of the receipt — check the amount.')
    }
  }
  return notes
}

/**
 * Whether a field the read failed a check on still holds what the read put
 * there — the editor outlines it until it doesn't. A person who changed it
 * has answered the check, and so has a bank row that replaced it.
 */
export function checkStillOpen(
  draft: AIJobDraft | undefined,
  field: AIJobDraftCheck,
  current: { date: string; cents: number | null }
): boolean {
  if (!draft?.checks?.includes(field)) return false
  if (field === 'date') return current.date === draft.date
  return current.cents === toCents(draft.amount)
}
