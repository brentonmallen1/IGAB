/** Pure math for the seasonality heatmap: cell lookup, color scale, and
 * value abbreviation. Extracted from SeasonalityHeatmap so it is
 * unit-testable. */

interface SeasonalityCellLike {
  category_id: string
  month: string
  total: string | number
}

/** Lookup keyed "categoryId|month" → numeric total. */
export function buildCellMap(cells: SeasonalityCellLike[]): Map<string, number> {
  const map = new Map<string, number>()
  for (const cell of cells) {
    map.set(`${cell.category_id}|${cell.month}`, Number(cell.total))
  }
  return map
}

/** Scale maximum; floored at 1 so an all-zero grid never divides by zero. */
export function maxCellValue(cells: SeasonalityCellLike[]): number {
  return Math.max(...cells.map((c) => Number(c.total)), 1)
}

/** Heat intensity for a cell, 0–100; null means "no heat" (empty cell). */
export function intensityPct(value: number, max: number): number | null {
  if (max === 0 || value === 0) return null
  return Math.round(Math.min(1, value / max) * 100)
}

/** Compact cell label: 1234 → "1.2k", 850 → "850". */
export function abbreviateValue(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toFixed(0)
}
