/**
 * Colour for a roadmap step.
 *
 * Uses the existing `--chart-1..8` categorical ramp — the only per-theme
 * colour set validated across all 40 variants for lightness band, chroma floor
 * and colourblind separation (see `themes/contrast.test.ts` and
 * `components/reports/charts/chartColors.ts`). No new tokens are introduced,
 * so the contrast suite needs no new assertions.
 *
 * Steps 1-6 take slots 1-6 in order. Step 0 is deliberately uncoloured: it is
 * the "before you start" group, and giving it a hue would imply it competes
 * with the others for attention.
 *
 * These colours appear on the rail, the dot and the connector only — never
 * behind text. That is what keeps them exempt from the 4.5:1 text rule while
 * still carrying the step identity.
 */
export function stepColor(step: number): string {
  if (step <= 0) return 'var(--text-muted)'
  const slot = Math.min(step, 6)
  return `var(--chart-${slot})`
}
