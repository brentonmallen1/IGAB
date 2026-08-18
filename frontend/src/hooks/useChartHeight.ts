import { useIsMobile } from './useMediaQuery'

/**
 * Chart height for the current viewport.
 *
 * recharts' ResponsiveContainer adapts width but takes height as a number, so
 * CSS cannot reach it. Desktop heights (340-500px) leave a phone showing one
 * chart and nothing else — no title, no surrounding context, no sense that
 * the page continues below. Capping at ~45% of the visible viewport keeps the
 * chart legible while the report around it stays readable.
 *
 * @param desktop the height the chart was designed at
 */
export function useChartHeight(desktop: number): number {
  const isMobile = useIsMobile()
  if (!isMobile) return desktop
  // window.innerHeight rather than a token: this is a JS number, and charts
  // are not re-measured on keyboard show/hide.
  const cap = Math.round(window.innerHeight * 0.45)
  return Math.max(220, Math.min(desktop, cap))
}
