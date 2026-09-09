/**
 * Money figures in an answer, found by the renderer rather than the model.
 *
 * The first version asked the model to backtick every amount. gemma wrote
 * `` `$`4,182.33` `` — the symbol alone in a code span and a stray backtick
 * after the digits — and rendered exactly that. A formatting rule that
 * depends on a small model's Markdown is a rule that is not enforced, so
 * the renderer finds the figures itself and repairs that mistake.
 *
 * MONEY mirrors `_MONEY` in backend/src/igab/ai/grounding.py: the same rule
 * decides which figures get styled here and which get checked there, and
 * `shared/money_figures.json` runs both against the same cases. Written
 * without lookbehind because the phone build has to run where that is not
 * guaranteed; the leading group is put back on replacement.
 */

const MONEY =
  /(^|[^\w.])(?:([$£€])\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)|(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2}))(?![\w%])/g

/** Every money amount in a piece of prose, as numeric strings, in order. */
export function extractFigures(text: string): string[] {
  const out: string[] = []
  for (const m of text.matchAll(MONEY)) {
    out.push((m[3] ?? m[4]).replace(/,/g, ''))
  }
  return out
}

/** The model's broken shape: symbol alone in a code span, digits outside. */
const SPLIT_SPAN = /`([$£€])`\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)`?/g

/** Fenced blocks and code spans, which are left exactly as written. */
const CODE = /(```[\s\S]*?```|`[^`\n]+`)/

/**
 * Markdown with every money figure in a code span and none of the model's
 * half-formed ones. Applied to the live answer and the persisted one alike,
 * so the text does not change shape when the stream lands.
 */
export function normalizeFigures(markdown: string): string {
  const repaired = markdown.replace(SPLIT_SPAN, '`$1$2`')
  return repaired
    .split(CODE)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(MONEY, (whole, lead: string) => `${lead}\`${whole.slice(lead.length)}\``)
    )
    .join('')
}
