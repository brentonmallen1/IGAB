import { afterAll, beforeAll } from 'vitest'

/**
 * Run a `describe` block in one IANA time zone, and put the runner's own zone
 * back afterwards. Call it at the top of the block.
 *
 * Restoring with `process.env.TZ = previous` is the trap it replaces: when the
 * runner had no TZ set — the normal case — that assigns the STRING
 * "undefined", which ICU reads as UTC. Every later test in the file then ran
 * in UTC, the one zone where these date bugs cannot be seen. The four copies
 * of that restore are now this one; unset stays unset.
 */
export function pinTimeZone(zone: string): void {
  let previous: string | undefined
  beforeAll(() => {
    previous = process.env.TZ
    process.env.TZ = zone
  })
  afterAll(() => {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  })
}
