import { type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import './Collapsible.css'

interface Props {
  title: string
  count?: number
  isOpen: boolean
  onToggle: () => void
  children: ReactNode
  className?: string
}

export function Collapsible({ title, count, isOpen, onToggle, children, className = '' }: Props) {
  const bodyId = `collapsible-${title.toLowerCase().replace(/\s+/g, '-')}`
  return (
    <div className={`collapsible ${className}`}>
      <button
        className="collapsible__header"
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls={bodyId}
      >
        <span className="collapsible__chevron">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="collapsible__title">{title}</span>
        {count !== undefined && (
          <span className="collapsible__count">{count}</span>
        )}
      </button>
      {isOpen && <div id={bodyId} className="collapsible__body">{children}</div>}
    </div>
  )
}
