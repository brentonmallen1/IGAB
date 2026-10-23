import {
  attentionLevel,
  attentionSummary,
  type AttentionCounts,
} from '../../../utils/accountAttention'

/**
 * One account's attention dot: warning when rows wait to be filed, info when
 * they wait only to be approved, a muted ring when rows are only pending,
 * nothing when the account is clear (utils/accountAttention). The shared
 * `.count-badge--dot` geometry; the surface it sits on picks the colour
 * through `--badge-warning` / `--badge-info` / `--badge-muted` (the sidebar
 * sets its own).
 */
const TONE = {
  categorize: 'count-badge--warning',
  approve: 'count-badge--info',
  pending: 'count-badge--muted',
} as const

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
  const tone = TONE[level]
  return (
    <span
      className={`count-badge count-badge--dot ${tone} ${className}`.trim()}
      role="img"
      aria-label={label}
      title={label}
    />
  )
}
