import './ChartLegend.css'

export interface LegendSeries {
  name: string
  color: string
  /** Optional figure shown beside the name — a legend that only names things
   *  makes the reader look somewhere else to find out which is which. */
  value?: string
}

/**
 * The key for a stacked chart, in stack order.
 *
 * Recharts' own `<Legend>` lays a centred row of full-size chips under the
 * chart and wraps it as far as it needs to. At four series that is fine; at
 * twelve it is several rows of chips that push the chart up, all competing
 * with it for attention, and it is still only a list of names.
 *
 * This is a dense grid instead: small swatches, one line each, its own
 * scrollable box so the chart's height never moves with the number of series.
 * The order matches the stack, so reading the bar bottom-to-top and the legend
 * top-to-bottom gives the same sequence.
 *
 * **It also carries identity the palette no longer can.** Eight themed slots
 * repeat past the eighth series (see chartColors.ts), so hovering an entry
 * dims the others — which is what makes a repeated colour unambiguous rather
 * than merely tolerable.
 */
export function ChartLegend({
  series,
  active,
  onHover,
}: {
  series: LegendSeries[]
  /** The series being highlighted, or null. */
  active: string | null
  onHover: (name: string | null) => void
}) {
  return (
    <ul
      className="chart-legend"
      onMouseLeave={() => onHover(null)}
      aria-label="Series in this chart"
    >
      {series.map((s) => (
        <li key={s.name}>
          <button
            type="button"
            className={`chart-legend__item ${active && active !== s.name ? 'is-dimmed' : ''}`}
            onMouseEnter={() => onHover(s.name)}
            onFocus={() => onHover(s.name)}
            onBlur={() => onHover(null)}
            // Highlighting is a pointer/focus affordance over a chart that is
            // already fully described by the table beneath it, so the button
            // does nothing on click rather than pretending to filter.
            aria-label={s.value ? `${s.name}, ${s.value}` : s.name}
          >
            <span className="chart-legend__swatch" style={{ backgroundColor: s.color }} />
            <span className="chart-legend__name">{s.name}</span>
            {s.value && <span className="chart-legend__value tabular">{s.value}</span>}
          </button>
        </li>
      ))}
    </ul>
  )
}
