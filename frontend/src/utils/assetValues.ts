/**
 * When a stated value reads as stale. 12 months — a MIRROR of the server's
 * one home for the threshold (`account_hygiene.STALE_ASSET_VALUE_MONTHS`,
 * which itself matches DORMANT_AFTER_MONTHS and the Guide's
 * STALE_EXTERNAL_MONTHS); the server raises the finding, this only tones the
 * "as of" line so the page agrees with the panel about the same date.
 */
export const VALUE_STALE_MONTHS = 12

export function isStaleValue(asOf: string | null, today: Date = new Date()): boolean {
  if (!asOf) return false
  const cutoff = new Date(today)
  cutoff.setMonth(cutoff.getMonth() - VALUE_STALE_MONTHS)
  return new Date(asOf + 'T00:00:00') < cutoff
}
