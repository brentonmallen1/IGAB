/**
 * The sentence under the account header when the bank's balance and the
 * ledger's cleared balance disagree.
 *
 * Pure, and colocated rather than inline, because the wording is the bug.
 * The page used to draw one sentence for every gap: "something may not have
 * been pulled in — fetch the last 90 days again from account settings".
 * That is true of exactly one of the three ways a gap arises, and it was
 * shown for all of them. On a Harborstone checking account reconciled clean,
 * it sent the user to spend one of twelve daily bridge requests looking for
 * transactions that were never missing — the ledger was AHEAD of the feed,
 * because they had ticked four holds cleared that the bank's own site
 * already showed as posted.
 *
 * Every fact here is served (backend: domain/bank_balance.py). Nothing is
 * re-derived: the same rule decides whether the sync calls a run degraded,
 * and a page that reached its own verdict would be free to disagree with
 * the sync badge.
 */

export interface DriftFacts {
  /** The bank's own figure. */
  reported: number
  /** Signed: positive when the bank holds more than the ledger says. */
  drift: number
  /** Signed, the part `unposted` does not account for. */
  unexplained: number
  /** Signed sum of cleared rows the bank has not posted against. */
  unposted: number
  reason: 'agree' | 'unposted' | 'stale' | 'unexplained'
  /** Whether the sync calls this a fault. Drives tone, never re-derived. */
  isFault: boolean
  /** The bank's balance date, already formatted, or null. */
  asOf: string | null
  /** Whether this account has ever been reconciled — chooses which way back
   *  to agreement the sentence names. */
  reconciled: boolean
}

export interface DriftNotice {
  tone: 'calm' | 'fault'
  text: string
}

/**
 * The notice, or null when there is nothing to say.
 *
 * `format` is the caller's money formatter, passed in so this module stays
 * free of locale and store wiring and every branch is a one-line test.
 */
export function bankDriftNotice(
  facts: DriftFacts,
  format: (value: number) => string
): DriftNotice | null {
  if (facts.reason === 'agree' || facts.drift === 0) return null

  const direction = facts.drift > 0 ? 'more' : 'less'
  const opening =
    `Bank reports ${format(facts.reported)} — ${format(Math.abs(facts.drift))} ` +
    `${direction} than the cleared balance here.`

  const tone: DriftNotice['tone'] = facts.isFault ? 'fault' : 'calm'

  if (facts.reason === 'unposted') {
    return {
      tone,
      text:
        `${opening} That is cleared spending the bank has not posted yet — ` +
        `it lines up on its own once the feed catches up.`,
    }
  }

  if (facts.reason === 'stale') {
    // Naming the date is the whole point: it is the one fact that says the
    // two figures are not measuring the same moment.
    const when = facts.asOf ? ` (${facts.asOf})` : ''
    return {
      tone,
      text:
        `${opening} The bank's figure${when} is older than the newest cleared ` +
        `row here, so the two are not measuring the same moment.`,
    }
  }

  // Unexplained — the only case where rows may genuinely be missing, and so
  // the only case that earns the refetch advice.
  const advice = facts.reconciled
    ? ' Something may not have been pulled in: fetch the last 90 days again from account settings, then reconcile.'
    : ' Reconcile to bring them together.'

  if (facts.unposted !== 0) {
    return {
      tone,
      text:
        `${opening} ${format(Math.abs(facts.unposted))} of that is cleared ` +
        `spending the bank has not posted yet; ${format(Math.abs(facts.unexplained))} ` +
        `is unaccounted for.${advice}`,
    }
  }

  return { tone, text: `${opening}${advice}` }
}
