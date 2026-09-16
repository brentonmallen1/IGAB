import { describe, expect, it } from 'vitest'

import type { SyncRun, SyncRunAccount } from '../../../api/syncLogs'
import { accountNote, runHeadline, runVerdict, windowDays } from './syncRunSummary'

function run(over: Partial<SyncRun> = {}): SyncRun {
  return {
    id: 'r1',
    connection_id: null,
    trigger: 'global',
    status: 'ok',
    window_start: null,
    window_end: null,
    duration_ms: 100,
    error: null,
    bank_errors: [],
    orphaned_links: [],
    feed_txn_count: 0,
    imported: 0,
    skipped: 0,
    skip_reasons: {},
    matched: 0,
    adopted: 0,
    cleared: 0,
    review_queued: 0,
    removed_pending: 0,
    anchored: 0,
    created_at: '2026-09-16T01:00:00Z',
    ...over,
  }
}

const ORPHAN = {
  account_id: 'a1',
  account_name: 'Harborstone Checking',
  stored_simplefin_id: 'ACT-old',
  suggested_feed_id: 'ACT-new',
  suggested_feed_name: 'HARBORSTONE EVERYDAY CHECKING',
}

describe('runVerdict', () => {
  it('calls a run with an orphaned link broken, even though it succeeded', () => {
    // The whole point: this run's status was "ok" for nine days.
    expect(runVerdict(run({ status: 'ok', orphaned_links: [ORPHAN], skipped: 586 }))).toBe('broken')
  })

  it('distinguishes a quiet run from a working one', () => {
    expect(runVerdict(run({ skipped: 512, skip_reasons: { already_posted: 512 } }))).toBe('quiet')
    expect(runVerdict(run({ imported: 3 }))).toBe('worked')
  })

  it('counts an adoption as work, not quiet', () => {
    expect(runVerdict(run({ adopted: 277 }))).toBe('worked')
  })

  it('reports failure and rate limiting separately', () => {
    expect(runVerdict(run({ status: 'error' }))).toBe('failed')
    expect(runVerdict(run({ status: 'rate_limited' }))).toBe('limited')
  })
})

describe('runHeadline', () => {
  it('names the account instead of counting skips', () => {
    expect(runHeadline(run({ orphaned_links: [ORPHAN], skipped: 586 }))).toContain(
      'Harborstone Checking'
    )
  })

  it('counts accounts when several are orphaned', () => {
    const headline = runHeadline(
      run({ orphaned_links: [ORPHAN, { ...ORPHAN, account_name: 'B' }] })
    )
    expect(headline).toContain('2 accounts')
  })

  it('says nothing new rather than showing zeroes', () => {
    expect(runHeadline(run({ skipped: 12 }))).toBe('Nothing new')
  })

  it('lists what a working run did', () => {
    expect(runHeadline(run({ imported: 53, adopted: 277 }))).toBe('53 imported, 277 re-linked')
  })
})

describe('windowDays', () => {
  it('reports the width the bridge was asked for', () => {
    expect(
      windowDays(run({ window_start: '2026-09-11T01:00:00Z', created_at: '2026-09-16T01:00:00Z' }))
    ).toBe(5)
  })

  it('shows an over-cap request, which the bridge silently caps', () => {
    const days = windowDays(
      run({ window_start: '2020-07-22T00:00:00Z', created_at: '2026-09-16T01:00:00Z' })
    )
    expect(days).toBeGreaterThan(90)
  })

  it('is null when no window was recorded', () => {
    expect(windowDays(run())).toBeNull()
  })
})

describe('accountNote', () => {
  function account(over: Partial<SyncRunAccount> = {}): SyncRunAccount {
    return {
      account_id: 'a1',
      account_name: 'Harborstone Checking',
      simplefin_account_id: 'ACT-old',
      feed_txn_count: 5,
      feed_oldest_date: null,
      feed_newest_date: null,
      imported: 0,
      adopted: 0,
      reidentified: false,
      orphaned: false,
      ...over,
    }
  }

  it('flags an orphaned account with what to do', () => {
    expect(accountNote(account({ orphaned: true }))).toContain('relink')
  })

  it('flags an account the feed returned nothing for', () => {
    expect(accountNote(account({ feed_txn_count: 0 }))).toContain('returned nothing')
  })

  it('explains an adoption', () => {
    expect(accountNote(account({ reidentified: true }))).toContain('adopted')
  })

  it('says nothing about an ordinary account', () => {
    expect(accountNote(account())).toBeNull()
  })
})
