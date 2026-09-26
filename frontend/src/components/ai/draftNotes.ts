import type { AIJob, AIJobDraft } from '../../api/aiJobs'

/** A category as a label can name it: its own name and its group's. */
export interface NamedCategory {
  name: string
  /** Null when the group is not in the list the caller holds. */
  group: string | null
}

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
export function categoryForLabel<C extends { name: string; category_group_id: string }>(
  label: string,
  categories: C[],
  groupNames: Map<string, string>
): C | undefined {
  return categories.find((c) =>
    labelNamesCategory(label, { name: c.name, group: groupNames.get(c.category_group_id) ?? null })
  )
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
 *  - `elsewhere` — the card that paid is on file for a different account;
 *  - `unknown` — the receipt printed an ending nobody has on file, so the
 *    review offers to remember it for this account.
 *  Null when the receipt showed no card, the scan has no account yet, or the
 *  ending is this account's own. Which account owns an ending is served
 *  (`card_ending_account_id`); this only compares two served ids. */
export type CardEndingNote =
  | { kind: 'elsewhere'; last4: string; ownerId: string; hereId: string }
  | { kind: 'unknown'; last4: string; hereId: string }

export function cardEndingNote(job: AIJob): CardEndingNote | null {
  const last4 = job.result?.draft?.card_last4
  const hereId = job.transaction_account_id
  if (!last4 || !hereId) return null
  const ownerId = job.card_ending_account_id
  if (!ownerId) return { kind: 'unknown', last4, hereId }
  if (ownerId !== hereId) return { kind: 'elsewhere', last4, ownerId, hereId }
  return null
}
