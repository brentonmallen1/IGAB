import { useContext, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { Surface, type SurfaceVariant } from '../common/Surface'
import { deltaTone, type GoodDirection } from './metricDelta'
import { MetricCompactContext } from './metricCompact'
import './MetricCard.css'

interface Props {
  label: string
  value: ReactNode
  /** A percentage change. `good` is required: the sign says which way the
   *  figure moved, and only the caller knows which way is good news
   *  (`metricDelta.ts`). */
  delta?: { value: number; label?: string; good: GoodDirection }
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
  const compact = useContext(MetricCompactContext)
  const tone = delta ? deltaTone(delta.value, delta.good) : 'neutral'

  // In a pinned header's summary: the label and the figure, and the warning
  // tone, which is the one piece of state a reader scrolling needs.
  if (compact) {
    return (
      <span className={`metric-summary__item${warning ? ' metric-summary__item--warning' : ''}`}>
        <span className="metric-summary__label">{label}</span>
        <span className="metric-summary__value">{value}</span>
      </span>
    )
  }

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
        <div className={`metric-card__delta metric-card__delta--${tone}`}>
          {delta.value > 0 ? '+' : ''}
          {delta.value.toFixed(1)}%
          {delta.label && <span className="metric-card__delta-label"> {delta.label}</span>}
        </div>
      )}
      {sub && <div className="metric-card__sub">{sub}</div>}
    </Surface>
  )
}
