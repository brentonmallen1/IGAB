import { useFormatters } from '../../hooks/useFormatters'
import { BADGE_LABELS, getTargetTooltip, type BadgeStatus } from './targetTooltip'
import './TargetBadge.css'

interface Props {
  status: BadgeStatus
  needed?: number
  checkDay?: number
  onClick?: () => void
}

export function TargetBadge({ status, needed, checkDay, onClick }: Props) {
  const { formatMoney } = useFormatters()
  const tooltip = getTargetTooltip(status, needed, formatMoney, checkDay)
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
