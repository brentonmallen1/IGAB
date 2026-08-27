/** Whether the viewer asked for less motion. One reading, so every scroll and
 *  sheet animation in the app answers the same way. */
export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}
