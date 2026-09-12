import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
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
  /**
   * Makes the whole tile open a dialog explaining the figure. `label` is the
   * button's accessible name — say what the figure reads and that it opens,
   * e.g. "Savings rate 18.5%. Show what contributed".
   *
   * The one clickable-card mechanism. The Overview's means card built it
   * privately — a button in the value slot stretched over the tile — and the
   * savings-rate cards needed the same; a second copy is how five anchored
   * dropdowns came to clamp in two different ways.
   */
  details?: { label: string; onOpen: () => void }
}

export function MetricCard({
  label,
  value,
  delta,
  sub,
  accent,
  warning,
  variant = 'sunken',
  details,
}: Props) {
  const deltaSign = delta && delta.value > 0 ? 'pos' : delta && delta.value < 0 ? 'neg' : 'neutral'

  const classes = ['metric-card']
  if (accent) classes.push('metric-card--accent')
  if (warning) classes.push('metric-card--warning')
  if (details) classes.push('metric-card--opens')

  return (
    <Surface variant={variant} className={classes.join(' ')}>
      <div className="metric-card__label">
        {label}
        {details && <ChevronRight className="metric-card__opens-icon" size={12} aria-hidden />}
      </div>
      <div className="metric-card__value">
        {details ? (
          // The button holds the value, not the card: a card inside a button
          // is invalid markup. Its ::after stretches over the tile, so the
          // click target is the whole of what a reader sees.
          <button
            type="button"
            className="metric-card__open"
            aria-haspopup="dialog"
            aria-label={details.label}
            onClick={details.onOpen}
          >
            {value}
          </button>
        ) : (
          value
        )}
      </div>
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
