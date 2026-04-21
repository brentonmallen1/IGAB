import { formatMoney } from '../../utils/money'
import './TargetBadge.css'

const LABELS = {
  funded: 'Funded',
  underfunded: 'Underfunded',
}

export function getTargetTooltip(status: 'funded' | 'underfunded', monthlyNeeded?: number): string {
  const showMonthly = monthlyNeeded !== undefined && monthlyNeeded > 0 && status !== 'funded'
  return showMonthly ? `Need ${formatMoney(monthlyNeeded!)}/mo to reach goal` : LABELS[status]
}

interface Props {
  status: 'funded' | 'underfunded'
  monthlyNeeded?: number
  onClick?: () => void
}

export function TargetBadge({ status, monthlyNeeded, onClick }: Props) {
  const showMonthly = monthlyNeeded !== undefined && monthlyNeeded > 0 && status !== 'funded'
  const tooltip = getTargetTooltip(status, monthlyNeeded)
  return (
    <span
      className={`target-badge target-badge--${status}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={tooltip}
    >
      {showMonthly ? `${formatMoney(monthlyNeeded!)}/mo` : LABELS[status]}
    </span>
  )
}
