/**
 * Chart color tokens — theme-aware CSS custom properties.
 *
 * The categorical slots (--chart-1..8) are defined per theme and validated
 * for chart use against each theme's surface (lightness band, chroma floor,
 * colorblind + normal-vision separation). Recharts accepts var() strings
 * directly as SVG fill/stroke values.
 *
 * Rules: assign slots in order. Semantic colors mark meaning
 * (positive/negative/net), never series identity.
 *
 * **Past the eighth series the palette repeats, and identity stops being the
 * colour's job.** This used to fold every ninth-plus series into one grey
 * "Other", which is a fine rule for a chart whose tail is noise and the wrong
 * one for a chart whose tail is money: Cost of Living stacked eight groups and
 * silently dropped the rest, so the bars and the table under them disagreed
 * about what a month cost.
 *
 * Repetition is the lesser cost, and only because something else carries the
 * identity: `ChartLegend` lists every series in stack order and highlights one
 * on hover, and the tooltip names the segment under the cursor. A chart that
 * repeats a colour without one of those is ambiguous — add the legend, or cap
 * the series before they reach here.
 *
 * Eight is the palette because each theme hand-picks eight slots that separate
 * for normal and colourblind vision on that theme's surface. A ninth token
 * would have to be authored forty times.
 */
export const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
  'var(--chart-7)',
  'var(--chart-8)',
]

export const COLOR_POSITIVE = 'var(--chart-positive)'
export const COLOR_NEGATIVE = 'var(--chart-negative)'
export const COLOR_NEUTRAL = 'var(--chart-neutral)'
export const COLOR_NET = 'var(--chart-net)'
export const COLOR_OTHER = 'var(--chart-other)'

/** Colour for the series at `index`, cycling once the palette runs out. See
 *  the note above: past the eighth, the legend carries identity, not the hue. */
export function chartColor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}

/** Shared tooltip style config for recharts Tooltip component.
 * Use when not using the custom ChartTooltip component. */
export const TOOLTIP_STYLE = {
  contentStyle: {
    background: 'var(--bg-elevated, var(--bg-secondary))',
    border: '1px solid var(--border-color)',
    borderRadius: 'var(--border-radius)',
    boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
    fontSize: 'var(--font-size-sm)',
    padding: 'var(--spacing-sm) var(--spacing-md)',
  },
  labelStyle: {
    color: 'var(--text-primary)',
    fontWeight: 600,
    marginBottom: 4,
  },
  itemStyle: {
    color: 'var(--text-secondary)',
    padding: '2px 0',
  },
  cursor: { fill: 'var(--row-hover-bg)' },
}
