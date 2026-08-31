/**
 * The health report's marker on a roadmap step: a small amber dot, present or
 * absent, nothing else.
 *
 * Two states only. No red — this is guidance, not an error, and a red dot on
 * someone's finances is the app raising its voice about something they did
 * not ask about. It does not animate, count, or badge the navigation; it
 * lives inside the Guide, where the reader has already chosen to look. The
 * reason travels with it so hovering answers the question and a screen
 * reader hears why rather than "image".
 */
export function StepLed({ reason }: { reason: string }) {
  return (
    <span className="guide-led" role="img" aria-label={`Worth a look: ${reason}`} title={reason} />
  )
}
