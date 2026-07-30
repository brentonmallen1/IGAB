/**
 * Chart color tokens — theme-aware CSS custom properties.
 *
 * The categorical slots (--chart-1..8) are defined per theme and validated
 * for chart use against each theme's surface (lightness band, chroma floor,
 * colorblind + normal-vision separation). Recharts accepts var() strings
 * directly as SVG fill/stroke values.
 *
 * Rules: assign slots in order, never cycle. A ninth-plus series carries no
 * distinguishable identity — fold it into "Other" (COLOR_OTHER). Semantic
 * colors mark meaning (positive/negative/net), never series identity.
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

/** Color for the series at `index`; series past the palette read as "Other". */
export function chartColor(index: number): string {
  return index < CHART_COLORS.length ? CHART_COLORS[index] : COLOR_OTHER
}
