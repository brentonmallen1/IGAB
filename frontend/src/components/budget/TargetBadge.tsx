import { useFormatters } from '../../hooks/useFormatters'
import { BADGE_LABELS, getTargetTooltip, type BadgeStatus } from './targetTooltip'
import './TargetBadge.css'

interface Props {
  status: BadgeStatus
  needed?: number
  checkDay?: number
  /** The target's stop ("Stop at $L"), named in the funded tooltip. */
  limit?: number | null
  onClick?: () => void
}

export function TargetBadge({ status, needed, checkDay, limit, onClick }: Props) {
  const { formatMoney } = useFormatters()
  const tooltip = getTargetTooltip(status, needed, formatMoney, checkDay, limit)
  const showAmount = status === 'underfunded' && needed !== undefined && needed > 0
  return (
    <span
      className={`target-badge target-badge--${status}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={tooltip}
    >
      {showAmount ? formatMoney(needed!) : BADGE_LABELS[status]}
    </span>
  )
}
