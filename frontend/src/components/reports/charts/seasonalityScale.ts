/** Pure math for the seasonality heatmap: cell lookup, colour scale, and
 * value abbreviation. Extracted from SeasonalityHeatmap so it is
 * unit-testable. */

import { PRIVACY_MASK } from '../../../utils/money'
import { compactMoney } from '../../../utils/moneyAxis'
import { categoryKey } from '../drillScope'

interface SeasonalityCellLike {
  /** null on the Uncategorized row. */
  category_id: string | null
  month: string
  total: string | number
}

/** The lookup key of one cell: its row's `categoryKey` and its month. */
export function cellKey(categoryId: string | null, month: string): string {
  return `${categoryKey(categoryId)}|${month}`
}

/** Lookup keyed by `cellKey` → numeric total. */
export function buildCellMap(cells: SeasonalityCellLike[]): Map<string, number> {
  const map = new Map<string, number>()
  for (const cell of cells) {
    map.set(cellKey(cell.category_id, cell.month), Number(cell.total))
  }
  return map
}

/**
 * Each row's busiest month — the top of that row's colour scale.
 *
 * **Row-normalised, not one scale for the grid.** The question the heatmap
 * answers is "when in the year does THIS category spike", and one scale over
 * every cell answered a different one: rent set the maximum, so every other
 * row sat in the palest shade and its own seasonality was invisible. The
 * numbers stay in the cells, so sizes are still read there.
 *
 * Keyed by `categoryKey`. A row with nothing positive — refunds only — has
 * no entry: none of its cells is heat.
 */
export function rowMaxima(cells: SeasonalityCellLike[]): Map<string, number> {
  const map = new Map<string, number>()
  for (const cell of cells) {
    const key = categoryKey(cell.category_id)
    const value = Number(cell.total)
    if (value > (map.get(key) ?? 0)) map.set(key, value)
  }
  return map
}

/** Heat intensity for a cell against its row's busiest month, 0–100; null
 *  means "no heat" — nothing spent, or refunds outweighing spending. */
export function intensityPct(value: number, rowMax: number | undefined): number | null {
  if (!rowMax || value <= 0) return null
  return Math.round(Math.min(1, value / rowMax) * 100)
}

/** Compact cell label: 1234 → "1.2k", 850 → "850", 2.4M → "2.4M".
 *
 * The axes' compact money without its symbol — a grid cell has no room for
 * one. It was its own formatter, which counted thousands forever ("2400.0k")
 * and rounded 12,345 to "12.3k" where the axis beside it said "12k".
 *
 * `masked` is required. It defaulted to false, the opt-in shape ChartTooltip
 * shed: a caller that forgot the flag printed real amounts in privacy mode
 * and nothing told it so. */
export function abbreviateValue(value: number, masked: boolean): string {
  if (masked) return PRIVACY_MASK
  return compactMoney(value, '')
}
