import type { ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useFormatters } from '../../../hooks/useFormatters'

interface Props {
  label: string
  /**
   * `section` — Budget Accounts / Assets / Liabilities.
   * `type` — a type group (Checking, Credit Cards) nested inside one.
   * Typography only: both sit in the same chevron/label/total column so the
   * whole sidebar reads as one list rather than three indent levels.
   */
  level: 'section' | 'type'
  /** Sum of exactly the rows this header covers, or null to draw no total. */
  total: number | null
  collapsed: boolean
  onToggle: () => void
  /** False when the group has no rows: the toggle is inert rather than absent,
   *  so the header keeps its geometry and the column stays straight. */
  collapsible?: boolean
  /** Where the label navigates, when it navigates. Given, the label is its own
   *  link and only the chevron toggles; omitted, the whole header toggles. */
  onLabelClick?: () => void
  labelTitle?: string
  /** Add / manage buttons, drawn after the total. */
  actions?: ReactNode
}

/**
 * The one group header in the sidebar.
 *
 * Sections and type groups were written separately and diverged: sections had a
 * total and an actions cluster, type groups had neither; two of the three
 * section labels were links and the third was a bare span; and the
 * no-liabilities case was a fourth copy that dropped the total and the actions
 * wrapper entirely. All of them are this component now, and `collapsible`
 * covers the empty case instead of a separate branch.
 */
export function SidebarGroupHeader({
  label,
  level,
  total,
  collapsed,
  onToggle,
  collapsible = true,
  onLabelClick,
  labelTitle,
  actions,
}: Props) {
  const { formatMoney } = useFormatters()

  const chevron = (
    <span className="sidebar__group-chevron" aria-hidden="true">
      {collapsible && (collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />)}
    </span>
  )
  const toggleTitle = collapsible
    ? collapsed
      ? `Expand ${label}`
      : `Collapse ${label}`
    : undefined

  return (
    <div className={`sidebar__group-header sidebar__group-header--${level}`}>
      {onLabelClick ? (
        <>
          <button
            className="sidebar__group-toggle sidebar__group-toggle--chevron-only"
            onClick={onToggle}
            disabled={!collapsible}
            aria-expanded={collapsible ? !collapsed : undefined}
            aria-label={toggleTitle}
            title={toggleTitle}
          >
            {chevron}
          </button>
          <button className="sidebar__group-label" onClick={onLabelClick} title={labelTitle}>
            {label}
          </button>
        </>
      ) : (
        <button
          className="sidebar__group-toggle"
          onClick={onToggle}
          disabled={!collapsible}
          aria-expanded={collapsible ? !collapsed : undefined}
          title={toggleTitle}
        >
          {chevron}
          <span className="sidebar__group-label">{label}</span>
        </button>
      )}
      <span className="sidebar__group-actions">
        {total !== null && (
          <span className={`sidebar__total tabular ${total < 0 ? 'negative' : ''}`}>
            {formatMoney(total)}
          </span>
        )}
        {actions}
      </span>
    </div>
  )
}
