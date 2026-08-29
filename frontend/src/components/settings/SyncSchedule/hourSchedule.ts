/**
 * Turning a stored sync schedule into the two ways a person thinks about one.
 *
 * The server stores exactly one thing: a list of UTC hours. "Every 4 hours"
 * and "at 07:00 and 19:00" are both just lists, which is what keeps the
 * scheduler down to a single question and leaves no second field to drift
 * against the first.
 *
 * What lives here is only presentation — which control to open, and what the
 * hour reads as on this person's clock. The server never decides either, and
 * it decides the schedule itself, so nothing here may become a second opinion
 * about when a sync runs.
 */

/** Intervals offered by the "every N hours" control — all divisors of 24. */
export const INTERVAL_CHOICES = [2, 3, 4, 6, 8, 12] as const

/** The UTC hours "every `every` hours, starting at `anchor`" comes out as. */
export function hoursForInterval(every: number, anchor: number): number[] {
  const hours: number[] = []
  for (let h = anchor % every; h < 24; h += every) hours.push(h)
  return hours.sort((a, b) => a - b)
}

/**
 * The interval a list of hours was (or could have been) authored as, or null
 * when it is just a set of times.
 *
 * Evenly spaced and covering the whole day is the test — [0, 6, 12, 18] is
 * every six hours, while [7, 19] is two chosen times even though the gaps are
 * equal, because it skips half the day. Anything else opens the times
 * control instead, which can express every schedule.
 */
export function deriveInterval(hours: number[]): number | null {
  if (hours.length < 2 || 24 % hours.length !== 0) return null
  const step = 24 / hours.length
  if (!(INTERVAL_CHOICES as readonly number[]).includes(step)) return null
  const sorted = [...hours].sort((a, b) => a - b)
  const expected = hoursForInterval(step, sorted[0])
  return expected.join() === sorted.join() ? step : null
}

/**
 * Local hour → the UTC hour to store, and back.
 *
 * `offsetMinutes` is `Date.prototype.getTimezoneOffset()`: minutes to ADD to
 * local time to reach UTC, so UTC-4 gives 240.
 *
 * Two limits, both deliberate and both stated in the UI. A stored UTC hour
 * does not follow daylight saving, so a schedule set in summer runs an hour
 * earlier (or later) in winter — for a bank sync that is not worth a stored
 * timezone. And in a half-hour zone the stored hour rounds, so the time shown
 * back can read :30 off the hour that was picked.
 */
export function localHourToUtcHour(localHour: number, offsetMinutes: number): number {
  return (((localHour + Math.round(offsetMinutes / 60)) % 24) + 24) % 24
}

export function utcHourToLocalHour(utcHour: number, offsetMinutes: number): number {
  return (((utcHour - Math.round(offsetMinutes / 60)) % 24) + 24) % 24
}
