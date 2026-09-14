import type { EssentialsFigures } from '../types'

/**
 * The essentials figure a surface is NOT headlining, said beside the one it
 * is — "$2,140.00/mo spread · $2,530.00/mo as paid".
 *
 * Both figures are served (`EssentialsFigures`); which one every target reads
 * is the budget's setting (`spread_on`), so the note leads with that one and
 * names both, so neither number appears without its label. When the two agree
 * — no Long-term expense bills in the windows — there is nothing to say, and
 * the note is null rather than a repeat of the headline.
 *
 * Presentation only: no arithmetic, the server decided both figures.
 */
export function otherFigureNote(
  figures: EssentialsFigures | null | undefined,
  formatMoney: (amount: number) => string
): string | null {
  if (!figures || figures.as_paid === figures.spread) return null
  const spread = `${formatMoney(figures.spread)}/mo spread`
  const asPaid = `${formatMoney(figures.as_paid)}/mo as paid`
  return figures.spread_on ? `${spread} · ${asPaid}` : `${asPaid} · ${spread}`
}
