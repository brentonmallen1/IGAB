import { X } from 'lucide-react'
import './FloatingSelectionBar.css'

interface ButtonProps {
  onClick: () => void
  disabled?: boolean
  title?: string
  children: React.ReactNode
}

function BarButton({ onClick, disabled, title, children }: ButtonProps) {
  return (
    <button className="fsb__btn" onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  )
}

function BarDivider() {
  return <div className="fsb__divider" />
}

interface Props {
  label: React.ReactNode
  sublabel?: React.ReactNode
  onClose: () => void
  children: React.ReactNode
}

export function FloatingSelectionBar({ label, sublabel, onClose, children }: Props) {
  return (
    <div className="fsb">
      <button
        className="fsb__close"
        onClick={onClose}
        title="Clear selection"
        aria-label="Clear selection"
      >
        <X size={14} />
      </button>
      <span className="fsb__label">{label}</span>
      {sublabel && <span className="fsb__sublabel">{sublabel}</span>}
      <BarDivider />
      {children}
    </div>
  )
}

FloatingSelectionBar.Button = BarButton
FloatingSelectionBar.Divider = BarDivider
