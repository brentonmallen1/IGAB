/**
 * The shared chart tooltip.
 *
 * `formatter` is required, and that is the point. It used to default to
 * ``$${value.toLocaleString('en-US', ...)}``, which meant three things at once:
 * every chart ignored the budget's currency and number format, every chart
 * ignored privacy mode — whose whole purpose is that "sign and digits hidden,
 * so overspending can't be inferred" — and the two charts whose series are not
 * money rendered a percentage and a month count as dollar amounts. Eighteen of
 * nineteen call sites had quietly acquired all of that by passing nothing.
 *
 * A default is how one mistake reaches nineteen call sites, so there is no
 * default. Pass `formatMoney` from `useFormatters()` for money, and an explicit
 * formatter for anything else; eslint refuses a `<ChartTooltip` without one.
 */
import './ChartTooltip.css'

interface TooltipEntry {
  name: string
  value: number
  color?: string
}

interface Props {
  active?: boolean
  payload?: { name: string; value: number; color?: string; fill?: string }[]
  label?: string
  /** How to render one entry. REQUIRED — see the note above.
   *
   * `name` is the series name, so a chart whose series are not all in the same
   * unit can branch on it. `SavingsRateChart` needs that: three money bars and
   * a percentage line share one tooltip.
   */
  formatter: (value: number, name: string) => string
  labelFormatter?: (label: string) => string
  showTotal?: boolean
  /** The wider set the listed rows are part of — a month's whole spend behind
   *  ten drawn series, say.
   *
   *  Same vocabulary as `DrillDownTable`, and the same rule: the Total line is
   *  the sum of the rows the tooltip LISTS, and a wider figure is drawn beside
   *  it. Spending Trends showed the ten drawn series' subtotal as "Total"
   *  inches above a table row headed All carrying a larger number. */
  wider?: { total: number; label: string }
}

export function ChartTooltip({
  active,
  payload,
  label,
  formatter,
  labelFormatter,
  showTotal = false,
  wider,
}: Props) {
  if (!active || !payload?.length) return null

  const entries: TooltipEntry[] = payload.map((p) => ({
    name: p.name,
    value: p.value,
    color: p.color ?? p.fill,
  }))

  const total = entries.reduce((s, e) => s + (e.value ?? 0), 0)
  const displayLabel = label ? (labelFormatter ? labelFormatter(label) : label) : null
  // A cent of rounding is not a truncated set.
  const partial = wider !== undefined && Math.abs(wider.total - total) >= 0.005

  return (
    <div className="chart-tooltip">
      {displayLabel && <div className="chart-tooltip__label">{displayLabel}</div>}
      {entries.map((entry, i) => (
        <div key={i} className="chart-tooltip__row">
          {entry.color && (
            <span className="chart-tooltip__swatch" style={{ background: entry.color }} />
          )}
          <span className="chart-tooltip__name">{entry.name}</span>
          <span className="chart-tooltip__value">{formatter(entry.value ?? 0, entry.name)}</span>
        </div>
      ))}
      {showTotal && entries.length > 1 && (
        <div className="chart-tooltip__row chart-tooltip__row--total">
          <span className="chart-tooltip__name">{partial ? 'Shown' : 'Total'}</span>
          <span className="chart-tooltip__value">{formatter(total, 'Total')}</span>
        </div>
      )}
      {partial && wider && (
        <div className="chart-tooltip__row chart-tooltip__row--total">
          <span className="chart-tooltip__name">{wider.label}</span>
          <span className="chart-tooltip__value">{formatter(wider.total, wider.label)}</span>
        </div>
      )}
    </div>
  )
}
