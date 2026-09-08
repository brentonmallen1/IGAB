/**
 * Which groups the stacked bar draws, and what happens to the rest.
 *
 * The chart drew `groups.slice(0, 8)` while the table below it listed every
 * group. Past the eighth, a group's money left the picture entirely: the stack
 * was short by however much it dropped, the legend never mentioned it, and the
 * two halves of one screen quietly disagreed about what a month cost.
 *
 * The cap itself is not the problem — eight is the palette, and a legend of
 * twenty is not a legend. Losing the money is. So the tail is summed into one
 * "Other" series: the stack keeps totalling the real figure, the legend stays
 * a fixed length however many groups a budget has, and the table beside it
 * remains the place to read the detail.
 */
export interface ChartGroup {
  group_name: string
  monthly_amounts: number[]
}

/** The palette has eight colours, and eight keys is about as much as a legend
 *  can carry before it stops being readable. */
export const MAX_CHART_SERIES = 8

export const OTHER_SERIES = 'Other'

export function chartSeries<T extends ChartGroup>(
  groups: T[],
  max = MAX_CHART_SERIES
): ChartGroup[] {
  if (groups.length <= max) return groups

  // One slot goes to the rollup, so `max - 1` are named individually. Groups
  // arrive sorted by size, so the tail is the small end.
  const named = groups.slice(0, max - 1)
  const rest = groups.slice(max - 1)
  const monthCount = groups[0]?.monthly_amounts.length ?? 0
  const other: ChartGroup = {
    group_name: OTHER_SERIES,
    monthly_amounts: Array.from({ length: monthCount }, (_, i) =>
      rest.reduce((sum, g) => sum + (g.monthly_amounts[i] ?? 0), 0)
    ),
  }
  return [...named, other]
}

/** How many groups "Other" stands for, for the note under the chart. */
export function rolledUpCount(groups: unknown[], max = MAX_CHART_SERIES): number {
  return groups.length <= max ? 0 : groups.length - (max - 1)
}
