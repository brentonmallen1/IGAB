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
  /** Pushed to the right of the header — a figure the group is about, so the
   *  total stays readable while the group is collapsed. */
  meta?: ReactNode
}

export function Collapsible({
  title,
  count,
  isOpen,
  onToggle,
  children,
  className = '',
  meta,
}: Props) {
  const bodyId = `collapsible-${title.toLowerCase().replace(/\s+/g, '-')}`
  // A closed section with rows in it is the one state where this header is the
  // *only* evidence its contents exist — so it stops being chrome and says so.
  // Register pending rows start collapsed, and a muted 11px uppercase label on
  // --surface-chrome read as a divider: a card payment sat unseen behind it.
  const hiding = !isOpen && count !== undefined && count > 0
  return (
    <div className={`collapsible ${className}`}>
      <button
        className={`collapsible__header${hiding ? ' collapsible__header--hiding' : ''}`}
        onClick={onToggle}
        aria-expanded={isOpen}
        aria-controls={bodyId}
      >
        <span className="collapsible__chevron">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="collapsible__title">{title}</span>
        {count !== undefined && <span className="collapsible__count">{count}</span>}
        {meta !== undefined && <span className="collapsible__meta">{meta}</span>}
      </button>
      {isOpen && (
        <div id={bodyId} className="collapsible__body">
          {children}
        </div>
      )}
    </div>
  )
}
