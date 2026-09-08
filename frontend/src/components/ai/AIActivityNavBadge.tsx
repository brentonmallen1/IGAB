import { aiBadgeLabel } from './aiBadge'
import { useAIBadgeState } from './useAIBadgeState'

/**
 * The badge on the AI Activity nav item: a count of transactions waiting for
 * approval, or a pulsing dot while the AI is working.
 *
 * One component for the sidebar and the More sheet. It replaces a pill in the
 * header, which was the only badge of its kind up there and pointed at a page
 * it did not look like it belonged to.
 */
export function AIActivityNavBadge() {
  const state = useAIBadgeState()
  if (state.kind === 'none') return null

  const label = aiBadgeLabel(state)
  const classes = [
    'count-badge',
    'count-badge--accent',
    state.kind === 'working' ? 'count-badge--dot' : '',
    state.working ? 'count-badge--working' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <span className={classes} title={label}>
      {state.kind === 'review' && <span aria-hidden="true">{state.count}</span>}
      <span className="sr-only">{label}</span>
    </span>
  )
}
