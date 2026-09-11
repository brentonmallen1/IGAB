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
import { drillDownFooter, type WiderSet } from '../drillDownTotals'
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
   *  ten drawn series, say. `label` is the plural noun, as on the drill table:
   *  the row reads "All categories".
   *
   *  The Total line is the sum of the rows the tooltip LISTS, and a wider
   *  figure is drawn beside it. Spending Trends showed the ten drawn series'
   *  subtotal as "Total" inches above a table row headed All carrying a larger
   *  number. The rule — what counts as partial, what heads the subtotal — is
   *  `drillDownFooter`'s, called here rather than re-typed: this tooltip had
   *  its own copy of the cent tolerance and its own wording ("Shown"). */
  wider?: WiderSet
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

  const footer = drillDownFooter(
    entries.map((e) => ({ amount: e.value ?? 0 })),
    wider,
    (amount) => formatter(amount, 'Total')
  )
  const displayLabel = label ? (labelFormatter ? labelFormatter(label) : label) : null
  const allLabel = wider?.label ? `All ${wider.label}` : 'All'

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
          <span className="chart-tooltip__name">{footer.totalLabel}</span>
          <span className="chart-tooltip__value">{formatter(footer.shown, 'Total')}</span>
        </div>
      )}
      {footer.wider !== null && (
        <div className="chart-tooltip__row chart-tooltip__row--total">
          <span className="chart-tooltip__name">{allLabel}</span>
          <span className="chart-tooltip__value">{formatter(footer.wider, allLabel)}</span>
        </div>
      )}
    </div>
  )
}
