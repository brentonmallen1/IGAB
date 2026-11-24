/**
 * What "Find possible duplicates" looks through.
 *
 * The scan used to take no questions: every row in the account against every
 * other, any age, reconciled or not. On an account with years behind it that
 * queued dozens of pairs that were two real charges, and each open pair holds
 * the account's reconciliation back until somebody answers it. So the scan
 * asks first, and starts from the narrow reading — recent rows that are not
 * reconciled, which is where a real duplicate lives.
 *
 * Pure: the dialog draws these, the store remembers the last answer, and the
 * page turns it into the request. Which pairs may be proposed at all is the
 * server's rule (`TransactionService.may_merge`), not restated here.
 */
import type { ConfirmRequest } from '../../stores/confirmStore'
import { toISODate, parseLocalDate } from '../../utils/dates'

export interface DuplicateScanScope {
  /** How many days back to look, or null for the whole account. */
  lookbackDays: number | null
  /** Also pair a reconciled row with one that is not. */
  includeReconciled: boolean
}

/** `label` is the choice in the dialog; `phrase` is the same span of time
 *  inside a sentence. Side by side, so a new choice cannot be given one and
 *  not the other — the phrase used to be worked out again from the number. */
export const LOOKBACK_CHOICES: { days: number | null; label: string; phrase: string }[] = [
  { days: 30, label: 'Last 30 days', phrase: 'in the last 30 days' },
  { days: 90, label: 'Last 90 days', phrase: 'in the last 90 days' },
  { days: 365, label: 'Last year', phrase: 'in the last year' },
  { days: null, label: 'All time', phrase: 'in this account' },
]

export const DEFAULT_DUPLICATE_SCAN_SCOPE: DuplicateScanScope = {
  lookbackDays: 90,
  includeReconciled: false,
}

/** A remembered scope, with anything this build does not offer read as the
 *  default — a hand-edited or older value must not send an unbounded scan. */
export function normalizeScanScope(saved: unknown): DuplicateScanScope {
  const s = (saved ?? {}) as Partial<DuplicateScanScope>
  const known = LOOKBACK_CHOICES.some((c) => c.days === s.lookbackDays)
  return {
    lookbackDays: known
      ? (s.lookbackDays as number | null)
      : DEFAULT_DUPLICATE_SCAN_SCOPE.lookbackDays,
    includeReconciled: s.includeReconciled === true,
  }
}

/** The first date the scan includes ("YYYY-MM-DD"), or undefined for all
 *  time. Local calendar days from `today` — never a UTC instant. */
export function scanSince(lookbackDays: number | null, today: string): string | undefined {
  if (lookbackDays === null) return undefined
  const d = parseLocalDate(today)
  d.setDate(d.getDate() - lookbackDays)
  return toISODate(d)
}

/** "in the last 90 days" — for the sentence that says a scan found nothing,
 *  so "nothing found" never reads as "nothing in the whole account". */
export function scopePhrase(scope: DuplicateScanScope): string {
  // A scope is always normalised to an offered choice before it is used.
  const where =
    LOOKBACK_CHOICES.find((c) => c.days === scope.lookbackDays)?.phrase ?? 'in this account'
  return scope.includeReconciled ? where : `${where}, reconciled ones aside`
}

/**
 * What to ask before every open pair is kept separate at once, or null when
 * there is nothing to ask: one pair is the review's own "Keep separate".
 * More than one used to go in a single click — most of them never looked
 * at, and a pair kept separate is never suggested again.
 */
export function keepAllSeparateQuestion(count: number): ConfirmRequest | null {
  if (count <= 1) return null
  return {
    title: `Keep all ${count} pairs separate?`,
    message:
      'None of them will be merged, and they won’t be suggested as duplicates again. ' +
      'You can undo this straight afterwards.',
    confirmLabel: `Keep ${count} separate`,
  }
}
