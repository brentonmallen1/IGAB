import {
  attentionLevel,
  attentionSummary,
  type AttentionCounts,
} from '../../../utils/accountAttention'

/**
 * One account's attention dot: warning when rows wait on the person, muted
 * when rows are only pending, nothing when the account is clear
 * (utils/accountAttention). The shared `.count-badge--dot` geometry; the
 * surface it sits on picks the colour through `--badge-warning` /
 * `--badge-muted` (the sidebar sets its own).
 */
export function AttentionDot({
  counts,
  className = '',
}: {
  counts: AttentionCounts
  /** Placement only — where the dot sits, never what it looks like. */
  className?: string
}) {
  const level = attentionLevel(counts)
  if (!level) return null
  const label = attentionSummary(counts)
  const tone = level === 'review' ? 'count-badge--warning' : 'count-badge--muted'
  return (
    <span
      className={`count-badge count-badge--dot ${tone} ${className}`.trim()}
      role="img"
      aria-label={label}
      title={label}
    />
  )
}
