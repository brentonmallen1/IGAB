/** Pure rules for the Plan vs Reality matrix's cells, apart from the
 * component so each branch is a one-line test. */
import type { CSSProperties } from 'react'
import type { PlanRealityCell } from '../../../types'
import { PRIVACY_MASK } from '../../../utils/money'
import { abbreviateValue } from './seasonalityScale'

/** A month is "active" when the plan or reality was non-zero — same rule the
 * backend uses for months_active/months_over. */
export function isActive(cell: PlanRealityCell): boolean {
  return cell.assigned !== 0 || cell.spent !== 0
}

/** An active cell's text: "−40" over plan, "+10" under, "0" on it.
 *
 * Masked, every active cell reads the mask alone, zero included. The sign
 * went outside the mask ("−••••" / "+••••") and an on-plan month read a
 * literal "0", so overspending could be read straight off a grid whose title
 * and cards said a sign-less "$••••" — which is what PRIVACY_MASK exists to
 * prevent.
 *
 * The overspend tint and the "over" weight stay in privacy mode, on purpose:
 * like every chart's bar heights and the Budget page's overspent colour, they
 * show state rather than a figure, and privacy mode masks figures. */
export function cellLabel(variance: number, masked: boolean): string {
  if (masked) return PRIVACY_MASK
  if (variance < 0) return `−${abbreviateValue(-variance, false)}`
  if (variance > 0) return `+${abbreviateValue(variance, false)}`
  return '0'
}

/** Overspend tint scaled by how bad the month was relative to the worst
 * overspend on screen — color only where there is genuine state. */
export function overspendStyle(variance: number, maxOver: number): CSSProperties {
  if (variance >= 0) return {}
  const pct = Math.round(Math.min(1, -variance / maxOver) * 30) + 8
  return { background: `color-mix(in srgb, var(--chart-negative) ${pct}%, transparent)` }
}
