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
  formatter?: (value: number) => string
  labelFormatter?: (label: string) => string
  showTotal?: boolean
}

const defaultFormatter = (value: number) =>
  `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export function ChartTooltip({
  active,
  payload,
  label,
  formatter = defaultFormatter,
  labelFormatter,
  showTotal = false,
}: Props) {
  if (!active || !payload?.length) return null

  const entries: TooltipEntry[] = payload.map((p) => ({
    name: p.name,
    value: p.value,
    color: p.color ?? p.fill,
  }))

  const total = entries.reduce((s, e) => s + (e.value ?? 0), 0)
  const displayLabel = label ? (labelFormatter ? labelFormatter(label) : label) : null

  return (
    <div className="chart-tooltip">
      {displayLabel && <div className="chart-tooltip__label">{displayLabel}</div>}
      {entries.map((entry, i) => (
        <div key={i} className="chart-tooltip__row">
          {entry.color && (
            <span className="chart-tooltip__swatch" style={{ background: entry.color }} />
          )}
          <span className="chart-tooltip__name">{entry.name}</span>
          <span className="chart-tooltip__value">{formatter(entry.value ?? 0)}</span>
        </div>
      ))}
      {showTotal && entries.length > 1 && (
        <div className="chart-tooltip__row chart-tooltip__row--total">
          <span className="chart-tooltip__name">Total</span>
          <span className="chart-tooltip__value">{formatter(total)}</span>
        </div>
      )}
    </div>
  )
}
