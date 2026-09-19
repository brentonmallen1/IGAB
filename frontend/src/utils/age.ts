/**
 * How long ago a timestamp was, in the words a person uses.
 *
 * The account header said "Reconciled 3 days ago" with its own arithmetic,
 * and the settings nav wants "3 days ago" beside Budget Backups. Two copies
 * of a floor-divide by 86,400,000 is how one of them ends up saying
 * "1 days ago".
 */

const DAY_MS = 24 * 60 * 60 * 1000

/** Whole calendar-ish days between then and now, never negative. */
export function ageDays(iso: string, now: number = Date.now()): number {
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / DAY_MS))
}

/** "today", "yesterday", "12 days ago". */
export function ageLabel(iso: string, now: number = Date.now()): string {
  const days = ageDays(iso, now)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}
