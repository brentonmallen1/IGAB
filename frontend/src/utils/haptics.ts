/**
 * Best-effort haptic tick for confirming actions on touch devices.
 * Android Chrome vibrates; iOS Safari has no vibration API and no-ops.
 */
export function hapticTick() {
  try {
    navigator.vibrate?.(10)
  } catch {
    // Some embedded webviews throw on vibrate — feedback is optional, never fatal
  }
}
