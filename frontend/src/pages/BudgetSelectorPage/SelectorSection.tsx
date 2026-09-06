import { ChevronDown, ChevronUp } from 'lucide-react'
import { Surface } from '../../components/common/Surface'

/**
 * A selector card whose header toggles its body. The Create / Import /
 * Sample forms used to sit in a cramped second column; collapsed sections
 * under the budget list give each form the page's full width — which is what
 * makes the YNAB account-mapping rows readable.
 */
export function SelectorSection({
  title,
  subtitle,
  open,
  onToggle,
  children,
  dashed = false,
}: {
  title: string
  subtitle: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
  /** Demoted affordance (the throwaway sample budget). */
  dashed?: boolean
}) {
  return (
    <Surface as="section" className="selector-card" dashed={dashed}>
      <button
        type="button"
        className="selector-card__header selector-card__header--toggle"
        onClick={onToggle}
        aria-expanded={open}
      >
        <div>
          <div className="section-label surface__title">{title}</div>
          <div className="selector-card__subtitle">{subtitle}</div>
        </div>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && children}
    </Surface>
  )
}
