import type { ReactNode } from 'react'
import { useFormatters } from '../../../hooks/useFormatters'
import { balanceTone } from './sidebarGroups'

interface Props {
  name: string
  /** Signed. What the sign MEANS depends on `kind` — see balanceTone. */
  balance: number
  /** Asset or debt. Passed rather than derived here so the liability rows,
   *  which have no Account to read a classification off, say it too. */
  kind: 'asset' | 'debt'
  onClick: () => void
  /** This row's page is the one open. Decided by `isRowActive` against the
   *  URL, never by the row itself — see sidebarGroups. */
  isActive?: boolean
  /** Liability mode marker (managed / manual); nothing elsewhere. */
  leadingIcon?: ReactNode
  /** Uncategorized count; 0 or absent draws no badge. */
  badgeCount?: number
  /** Row-level action drawn before the balance — sync status, register shortcut. */
  trailing?: ReactNode
}

/**
 * The one account row in the sidebar.
 *
 * There were three of these — on-budget, assets, liabilities — and they had
 * drifted the way the copies in this repo always do: only two wrapped the
 * right-hand side in `.sidebar__account-right`, so asset balances sat at a
 * different distance from the name than every other row, and only two passed a
 * `negative` class, so an asset with a negative balance rendered in the same
 * muted grey as a positive one. A budgeting app that shows a debt in the colour
 * of a surplus is the drift that costs trust.
 *
 * The balance sits in a chip rather than as bare text: a long name truncated
 * right up against a number was two columns reading as one, and the chip is
 * where the tone lives when there is one to show.
 *
 * Rendered as `div role="button"` rather than `<button>` in every case,
 * including rows with no nested control: the liability rows contain a real
 * `<button>` for the register shortcut, and a button inside a button is invalid
 * HTML. One shape for all rows beats two that must be picked between.
 */
export function SidebarAccountRow({
  name,
  balance,
  kind,
  onClick,
  isActive = false,
  leadingIcon,
  badgeCount = 0,
  trailing,
}: Props) {
  const { formatMoney } = useFormatters()
  const tone = balanceTone(balance, kind)

  return (
    <div
      className={`sidebar__account ${isActive ? 'sidebar__account--active' : ''}`}
      role="button"
      tabIndex={0}
      // `page` rather than `true`: this row IS the page being shown, which is
      // what the nav items above already claim via NavLink.
      aria-current={isActive ? 'page' : undefined}
      title={name}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
    >
      <span className="sidebar__account-name">
        {leadingIcon}
        <span className="sidebar__account-label">{name}</span>
        {badgeCount > 0 && (
          <span
            className="sidebar__uncategorized-badge"
            title={`${badgeCount} uncategorized`}
          >
            {badgeCount}
          </span>
        )}
      </span>
      <span className="sidebar__account-right">
        {trailing}
        <span className={`sidebar__account-balance tabular sidebar__account-balance--${tone}`}>
          {formatMoney(balance)}
        </span>
      </span>
    </div>
  )
}
