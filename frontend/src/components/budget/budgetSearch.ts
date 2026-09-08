/**
 * What the budget bar's filter box means, including `tag:`.
 *
 * The box matched a category name or its group's name and nothing else, so the
 * one grouping the budget already has — tags, the same ones saved filters are
 * built from — could not be reached without saving a filter first.
 *
 * **Why this is not in `searchParser.ts`.** Every token there (`category:`,
 * `is:`, `amount:`) selects transactions and means the same thing in the
 * command palette as in the register's own box. `tag:` here selects budget
 * rows, so it would be offered in a box where it does nothing — the reasoning
 * `categoryFilterCommand.ts` already wrote down for the same page. Its
 * tokenizer IS shared, because quote handling is a rule and not a preference.
 *
 * **Why matching `cat.tags` on the client is not the tag→category resolution
 * the server owns.** A saved filter's members come back as
 * `category_ids_effective` and are never re-derived here — that union answers
 * "which categories belong to this saved filter", which reports and the grid
 * must agree on. This reads `Category.tags`, a field already served on every
 * row, and narrows rows the grid has *already* decided to draw. It has exactly
 * the standing of the name needle beside it.
 *
 * The two therefore differ, deliberately, in one place: a hidden or archived
 * category carrying the tag is in the server's union and is not on screen
 * here, because the grid never draws it. `tag:` narrows what you can see; it
 * does not reveal.
 */
import { tokenize } from '../../utils/searchParser'

export interface BudgetSearch {
  /** Free text, lowercased — matches a category or group name. */
  text: string
  /** Lowercased tag needles; a category matching ANY of them passes. */
  tagNames: string[]
}

/** A category as this module needs to see it. */
interface SearchableCategory {
  name: string
  tags?: { name: string }[]
}

//: `tag:x` and `tag: x` both, because both are what people type — the same
//: pair `categoryFilterCommand` accepts for `filter:`.
const TAG_TOKEN = /^tag:(.*)$/i

function unquote(value: string): string {
  const trimmed = value.trim()
  return trimmed.startsWith('"') ? trimmed.replace(/^"|"$/g, '') : trimmed
}

export function parseBudgetSearch(query: string): BudgetSearch {
  const tokens = tokenize(query)
  const tagNames: string[] = []
  const words: string[] = []

  for (let i = 0; i < tokens.length; i++) {
    const match = TAG_TOKEN.exec(tokens[i])
    if (!match) {
      words.push(tokens[i])
      continue
    }
    const inline = unquote(match[1])
    if (inline) {
      tagNames.push(inline.toLowerCase())
    } else if (i + 1 < tokens.length) {
      // The spaced form: `tag:` carried no value, so the next token is it.
      tagNames.push(unquote(tokens[++i]).toLowerCase())
    }
    // A trailing bare `tag:` narrows nothing — it is a half-typed query, and
    // blanking the grid mid-keystroke is not an answer to it.
  }

  return { text: unquote(words.join(' ')).toLowerCase(), tagNames }
}

/** Whether the box is narrowing anything at all. */
export function isBudgetSearchActive(search: BudgetSearch): boolean {
  return search.text !== '' || search.tagNames.length > 0
}

/**
 * Does this category survive the box? Tags AND text — `tag:essential rent`
 * means an Essential category matching "rent", which is the reading that makes
 * the two useful together. Multiple tags OR, matching how a saved filter's
 * `tag_ids` union rather than intersect.
 */
export function matchesBudgetSearch(
  category: SearchableCategory,
  search: BudgetSearch,
  groupName: string
): boolean {
  if (search.tagNames.length > 0) {
    const tags = category.tags ?? []
    const tagged = tags.some((t) =>
      search.tagNames.some((needle) => t.name.toLowerCase().includes(needle))
    )
    if (!tagged) return false
  }
  if (search.text === '') return true
  return (
    category.name.toLowerCase().includes(search.text) ||
    groupName.toLowerCase().includes(search.text)
  )
}
