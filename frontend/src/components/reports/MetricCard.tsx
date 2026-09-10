import type { ReactNode } from 'react'
import { Surface, type SurfaceVariant } from '../common/Surface'
import './MetricCard.css'

interface Props {
  label: string
  value: ReactNode
  delta?: { value: number; label?: string }
  sub?: ReactNode
  // `trend?: 'up' | 'down' | 'neutral'` lived here, declared and never
  // rendered. One caller passed it — the Emergency Fund's coverage card — and
  // its `sub` already states the direction in words ("+1 months over 12
  // months"), so nothing was lost on screen and nothing gained by keeping a
  // prop that does nothing. Dead code encoding an unbuilt feature is worse
  // than no code, because the next reader will pass it and expect an arrow.
  accent?: boolean
  warning?: boolean
  /**
   * Metric tiles usually sit inside a raised report section, where they read
   * as sunken wells. On the page canvas (LiabilityPage) pass `raised`.
   */
  variant?: Extract<SurfaceVariant, 'raised' | 'sunken'>
}

export function MetricCard({
  label,
  value,
  delta,
  sub,
  accent,
  warning,
  variant = 'sunken',
}: Props) {
  const deltaSign = delta && delta.value > 0 ? 'pos' : delta && delta.value < 0 ? 'neg' : 'neutral'

  const classes = ['metric-card']
  if (accent) classes.push('metric-card--accent')
  if (warning) classes.push('metric-card--warning')

  return (
    <Surface variant={variant} className={classes.join(' ')}>
      <div className="metric-card__label">{label}</div>
      <div className="metric-card__value">{value}</div>
      {delta !== undefined && (
        <div className={`metric-card__delta metric-card__delta--${deltaSign}`}>
          {delta.value > 0 ? '+' : ''}
          {delta.value.toFixed(1)}%
          {delta.label && <span className="metric-card__delta-label"> {delta.label}</span>}
        </div>
      )}
      {sub && <div className="metric-card__sub">{sub}</div>}
    </Surface>
  )
}
