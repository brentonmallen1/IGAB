import type { HygieneFinding } from '../../api/accounts'

/**
 * Findings whose rows are each their own news. Dismissing one of these hides
 * the rows it listed, not the kind: "No longer at the bank" dismissed today
 * must still speak up when next week's hold drops off.
 */
const PER_ROW_KINDS = new Set(['no_longer_at_bank'])

/** What dismissing this finding records — its kind, or one key per row. */
export function dismissalKeys(f: HygieneFinding): string[] {
  if (!PER_ROW_KINDS.has(f.kind)) return [f.kind]
  return f.items.map((item) => `${f.kind}:${item.transaction_id ?? item.label}`)
}

/** Hidden when everything it is about has been dismissed. A per-row finding
 *  with one new row comes back whole, so its counts and its list agree. */
export function isDismissed(f: HygieneFinding, dismissed: readonly string[]): boolean {
  const keys = dismissalKeys(f)
  return keys.length > 0 && keys.every((k) => dismissed.includes(k))
}
