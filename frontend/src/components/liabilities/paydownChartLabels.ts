/**
 * Where a reference line's label may be drawn without falling off the chart.
 *
 * Recharts centres a `position: 'top'` label on its line, so a line at either
 * end of the axis loses half its label to the plot edge — the paydown chart's
 * "Live payoff" marker sits on the payoff month, which is the last point on
 * the axis, and read as "Live payo". The three markers on that chart (Today,
 * Promo ends, Live payoff) each wrote the same `position: 'top'` label object,
 * so the one that clipped was the one that happened to sit at the edge.
 *
 * Pure on purpose: it takes the month list rather than reading the chart, so
 * every branch is a one-line test.
 */

/**
 * How close to an end counts as "at the edge", as a share of the axis.
 *
 * Deliberately narrow. Clipping is a pixel fact and this is a proportional
 * proxy for it, so the band is sized to catch the extreme points and leave
 * everything else centred: at 0.12 a marker on the second of twelve months
 * was anchored too, and it sits a tenth of the way across a plot hundreds of
 * pixels wide, nowhere near an edge.
 */
const EDGE_BAND = 0.05

export type LabelAnchor = 'start' | 'middle' | 'end'

/**
 * The text anchor that keeps a label on the plot: a marker in the leftmost
 * band grows rightward, one in the rightmost band grows leftward, and
 * anything in between stays centred on its line.
 *
 * A month the axis does not draw returns 'middle' — the caller does not draw
 * the line at all in that case.
 */
export function referenceLabelAnchor(month: string, months: readonly string[]): LabelAnchor {
  const i = months.indexOf(month)
  if (i < 0 || months.length < 2) return 'middle'
  const position = i / (months.length - 1)
  if (position <= EDGE_BAND) return 'start'
  if (position >= 1 - EDGE_BAND) return 'end'
  return 'middle'
}

/**
 * The label object for a paydown reference line — one shape for all three
 * markers, so none of them can quietly lose the clamp the others have.
 */
export function referenceLabel(
  value: string,
  month: string,
  months: readonly string[],
  fill: string
) {
  return {
    value,
    fontSize: 11,
    fill,
    position: 'top' as const,
    textAnchor: referenceLabelAnchor(month, months),
  }
}
