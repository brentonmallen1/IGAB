import { useFormatters } from '../../hooks/useFormatters'
import './TargetBadge.css'

const LABELS = {
  funded: 'Funded',
  underfunded: 'Underfunded',
}

export function getTargetTooltip(
  status: 'funded' | 'underfunded',
  monthlyNeeded: number | undefined,
  formatMoney: (amount: number) => string
): string {
  const showMonthly = monthlyNeeded !== undefined && monthlyNeeded > 0 && status !== 'funded'
  return showMonthly ? `Need ${formatMoney(monthlyNeeded!)}/mo to reach goal` : LABELS[status]
}

interface Props {
  status: 'funded' | 'underfunded'
  monthlyNeeded?: number
  onClick?: () => void
}

export function TargetBadge({ status, monthlyNeeded, onClick }: Props) {
  const { formatMoney } = useFormatters()
  const showMonthly = monthlyNeeded !== undefined && monthlyNeeded > 0 && status !== 'funded'
  const tooltip = getTargetTooltip(status, monthlyNeeded, formatMoney)
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
