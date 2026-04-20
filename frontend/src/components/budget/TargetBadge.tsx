import './TargetBadge.css'

interface Props {
  status: 'funded' | 'underfunded' | 'overfunded'
  onClick?: () => void
}

const LABELS = {
  funded: 'Funded',
  underfunded: 'Underfunded',
  overfunded: 'Overfunded',
}

export function TargetBadge({ status, onClick }: Props) {
  return (
    <span
      className={`target-badge target-badge--${status}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {LABELS[status]}
    </span>
  )
}
