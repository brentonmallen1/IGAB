/**
 * The sentence the account header draws when the bank and the ledger
 * disagree — one case per cause, because the bug was that all three got the
 * same one.
 *
 * The case on record: a Harborstone checking account, reconciled clean, with
 * the bank reporting $120.00 more than the cleared balance. $95.00 of that
 * was four holds the user had ticked cleared because the bank's own site
 * showed them posted while the feed still called them pending; $25.00 was a
 * row they had typed by hand. The page said "something may not have been
 * pulled in — fetch the last 90 days again", which was wrong about the
 * direction and would have burned one of twelve daily bridge requests.
 *
 * Figures are invented and rescaled — see the personal-data rule in
 * CLAUDE.md.
 */

import { describe, it, expect } from 'vitest'
import { bankDriftNotice, type DriftFacts } from './bankDriftNotice'

const money = (v: number) => `$${v.toFixed(2)}`

const facts = (over: Partial<DriftFacts> = {}): DriftFacts => ({
  reported: 8420,
  drift: 120,
  unexplained: 120,
  unposted: 0,
  reason: 'unexplained',
  isFault: true,
  asOf: null,
  reconciled: true,
  ...over,
})

describe('nothing to say', () => {
  it('draws no line when the figures agree', () => {
    expect(bankDriftNotice(facts({ reason: 'agree', drift: 0 }), money)).toBeNull()
  })

  it('draws no line for a zero gap whatever the reason says', () => {
    expect(bankDriftNotice(facts({ drift: 0 }), money)).toBeNull()
  })
})

describe('the ledger is ahead of the feed', () => {
  const unposted = facts({
    reported: 8395,
    drift: 120,
    unexplained: 0,
    unposted: -95,
    reason: 'unposted',
    isFault: false,
  })

  it('says the bank has not posted it yet', () => {
    const notice = bankDriftNotice(unposted, money)
    expect(notice?.text).toContain('has not posted yet')
    expect(notice?.text).toContain('lines up on its own')
  })

  it('never sends the user to refetch — the regression this exists for', () => {
    expect(bankDriftNotice(unposted, money)?.text).not.toContain('90 days')
  })

  it('reads calm, not as a fault', () => {
    expect(bankDriftNotice(unposted, money)?.tone).toBe('calm')
  })
})

describe('the bank figure is stale', () => {
  const stale = facts({
    reason: 'stale',
    isFault: false,
    asOf: 'Sep 18, 2026 2:00 PM',
  })

  it('names the date, which is the whole point', () => {
    expect(bankDriftNotice(stale, money)?.text).toContain('Sep 18, 2026 2:00 PM')
  })

  it('says the two are not measuring the same moment', () => {
    expect(bankDriftNotice(stale, money)?.text).toContain('not measuring the same moment')
  })

  it('does not send the user to refetch', () => {
    expect(bankDriftNotice(stale, money)?.text).not.toContain('90 days')
  })

  it('survives a missing formatted date', () => {
    const notice = bankDriftNotice(facts({ reason: 'stale', isFault: false }), money)
    expect(notice?.text).toContain('is older than the newest cleared row')
    expect(notice?.text).not.toContain('()')
  })
})

describe('a gap nothing accounts for', () => {
  it('keeps the refetch advice on a reconciled account', () => {
    const notice = bankDriftNotice(facts(), money)
    expect(notice?.text).toContain('fetch the last 90 days again')
    expect(notice?.tone).toBe('fault')
  })

  it('asks an unreconciled account to reconcile instead', () => {
    const notice = bankDriftNotice(facts({ reconciled: false, isFault: false }), money)
    expect(notice?.text).toContain('Reconcile to bring them together')
    expect(notice?.text).not.toContain('90 days')
  })

  it('splits a partly-explained gap into both figures', () => {
    /** The incident exactly: $95.00 accounted for, $25.00 not. */
    const notice = bankDriftNotice(facts({ unposted: -95, unexplained: 25 }), money)
    expect(notice?.text).toContain('$95.00 of that is cleared spending the bank has not posted')
    expect(notice?.text).toContain('$25.00 is unaccounted for')
    expect(notice?.text).toContain('fetch the last 90 days again')
  })

  it('says nothing about unposted rows when there are none', () => {
    expect(bankDriftNotice(facts(), money)?.text).not.toContain('unaccounted for')
  })
})

describe('direction', () => {
  it('reads "more" when the bank holds more', () => {
    expect(bankDriftNotice(facts({ drift: 120 }), money)?.text).toContain(
      '$120.00 more than the cleared balance'
    )
  })

  it('reads "less" when the bank holds less', () => {
    /** The direction that DOES mean rows may be missing. */
    expect(bankDriftNotice(facts({ drift: -120, unexplained: -120 }), money)?.text).toContain(
      '$120.00 less than the cleared balance'
    )
  })
})
