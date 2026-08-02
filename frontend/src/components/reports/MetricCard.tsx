import type { ReactNode } from 'react'
import './MetricCard.css'

interface Props {
  label: string
  value: ReactNode
  delta?: { value: number; label?: string }
  sub?: ReactNode
  trend?: 'up' | 'down' | 'neutral'
  accent?: boolean
  warning?: boolean
}

export function MetricCard({ label, value, delta, sub, accent, warning }: Props) {
  const deltaSign = delta && delta.value > 0 ? 'pos' : delta && delta.value < 0 ? 'neg' : 'neutral'

  const classes = ['metric-card']
  if (accent) classes.push('metric-card--accent')
  if (warning) classes.push('metric-card--warning')

  return (
    <div className={classes.join(' ')}>
      <div className="metric-card__label">{label}</div>
      <div className="metric-card__value">{value}</div>
      {delta !== undefined && (
        <div className={`metric-card__delta metric-card__delta--${deltaSign}`}>
          {delta.value > 0 ? '+' : ''}{delta.value.toFixed(1)}%
          {delta.label && <span className="metric-card__delta-label"> {delta.label}</span>}
        </div>
      )}
      {sub && <div className="metric-card__sub">{sub}</div>}
    </div>
  )
}
