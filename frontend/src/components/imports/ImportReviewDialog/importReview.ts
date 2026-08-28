/**
 * What the import review is showing, and what pressing Done would write.
 *
 * Pure: no hooks, no query client, no DOM. The dialog does the fetching and
 * the rendering; every rule about which steps exist, which rows are worth
 * showing and what counts as a change lives here, where it is a one-line test.
 */

import type { TagSuggestion } from '../../../api/tags'
import type { YnabImportResult, YnabTaggedCategory } from '../../../api/imports'

export type StepId = 'summary' | 'tags' | 'accounts'

/**
 * Which steps this budget has.
 *
 * A budget with no stored summary — one created by hand, or imported before
 * IGAB kept a record — skips straight to what can still be changed. That is
 * the case the review is most useful for: those budgets have no tags at all.
 */
export function stepsFor(summary: YnabImportResult | null | undefined): StepId[] {
  return summary ? ['summary', 'tags', 'accounts'] : ['tags', 'accounts']
}

export interface ReviewCategory {
  id: string
  name: string
  groupName: string
  hidden: boolean
  /** Every tag the category carries — system and the user's own alike. */
  tagIds: string[]
}

export interface RowSuggestion {
  systemKey: string
  matchedOn: string
}

export interface ReviewRow {
  category: ReviewCategory
  /** System keys it carries now, in the draft. */
  held: string[]
  /** Keys its names point at that it does not carry. */
  suggestions: RowSuggestion[]
  /** This import put a tag on it — the rows the review opens on. */
  importTagged: boolean
  /** The name that made the import's guess, so it can be checked. */
  importMatchedOn: string | null
}

/** Tag id -> system key, for the budget's tags. Only system tags have one. */
export type SystemKeyById = Record<string, string>

function heldKeys(tagIds: string[], keyById: SystemKeyById): string[] {
  return tagIds.map((id) => keyById[id]).filter((key): key is string => Boolean(key))
}

/**
 * One row per category, merging what it carries with what is proposed.
 *
 * Suggestions the category already carries are dropped rather than shown as
 * unchecked — the server filters them too, but the draft moves under the user
 * as they work, and an accepted proposal that stayed in the list would read as
 * though it had not applied.
 */
export function buildRows(
  categories: ReviewCategory[],
  suggestions: TagSuggestion[],
  tagged: YnabTaggedCategory[],
  keyById: SystemKeyById,
  draft: Draft
): ReviewRow[] {
  const byCategory = new Map<string, RowSuggestion[]>()
  for (const s of suggestions) {
    const list = byCategory.get(s.category_id) ?? []
    list.push({ systemKey: s.system_key, matchedOn: s.matched_on })
    byCategory.set(s.category_id, list)
  }
  const importedBy = new Map(tagged.map((t) => [t.category_id, t]))

  return categories.map((category) => {
    const held = heldKeys(draft[category.id] ?? category.tagIds, keyById)
    const fromImport = importedBy.get(category.id)
    return {
      category,
      held,
      suggestions: (byCategory.get(category.id) ?? []).filter((s) => !held.includes(s.systemKey)),
      importTagged: fromImport !== undefined,
      importMatchedOn: fromImport?.matched_on ?? null,
    }
  })
}

export type RowFilter = 'decided' | 'suggested' | 'all'

/**
 * Which filter the tag step opens on.
 *
 * "What the import decided" is the right first view only when there was an
 * import that decided something. A budget with no stored summary — reopened
 * from Settings, or built by hand — has no such rows, and defaulting to them
 * would open the step on an empty list. Those are precisely the budgets with
 * no tags at all, so they open on what is being proposed instead.
 */
export function initialFilter(summary: YnabImportResult | null | undefined): RowFilter {
  return summary && summary.tagged_categories.length > 0 ? 'decided' : 'suggested'
}

/**
 * Which rows a filter shows.
 *
 * 'decided' is the review's opening view: the categories the import tagged,
 * plus any the user has changed in this sitting so a row never vanishes as it
 * is being worked on.
 */
export function filterRows(rows: ReviewRow[], filter: RowFilter, draft: Draft): ReviewRow[] {
  if (filter === 'all') return rows
  if (filter === 'suggested') return rows.filter((r) => r.suggestions.length > 0)
  return rows.filter((r) => r.importTagged || r.category.id in draft)
}

/** Category id -> its full intended tag set. Absent means untouched. */
export type Draft = Record<string, string[]>

/**
 * Add or remove one tag on a category, seeding from what it carries now.
 *
 * The whole set is carried because the server replaces rather than merges: a
 * draft holding only the system tag being changed would silently drop the
 * user's own tags on that category.
 */
export function toggleTag(draft: Draft, category: ReviewCategory, tagId: string): Draft {
  const current = draft[category.id] ?? category.tagIds
  const next = current.includes(tagId)
    ? current.filter((id) => id !== tagId)
    : [...current, tagId]
  return { ...draft, [category.id]: next }
}

/** Order-insensitive: the draft appends, the server returns sorted by name. */
function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  const inB = new Set(b)
  return a.every((id) => inB.has(id))
}

/**
 * What Done would send: only the categories whose tag set actually moved.
 *
 * A row toggled on and back off again is not a change, and sending it would
 * rewrite a category the user decided to leave alone.
 */
export function pendingUpdates(
  draft: Draft,
  categories: ReviewCategory[]
): { category_id: string; tag_ids: string[] }[] {
  const byId = new Map(categories.map((c) => [c.id, c]))
  return Object.entries(draft)
    .filter(([id, tagIds]) => {
      const category = byId.get(id)
      return category !== undefined && !sameSet(tagIds, category.tagIds)
    })
    .map(([category_id, tag_ids]) => ({ category_id, tag_ids }))
}

/**
 * The unpaired transfer legs worth chasing.
 *
 * Split legs are counted into the total because they are real rows the user
 * can see, but they can never be paired — a split's money lives on its parent,
 * so linking a child would put the pair's halves at different levels. Saying
 * "1,117 unmatched" when 200 of them are unmatchable is how a number becomes
 * a chore nobody finishes.
 */
export function repairableTransferLegs(summary: YnabImportResult): number {
  return Math.max(0, summary.transfer_legs_unpaired - summary.transfer_legs_in_splits)
}
