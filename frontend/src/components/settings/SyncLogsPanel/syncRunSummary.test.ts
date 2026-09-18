import { describe, expect, it } from 'vitest'

import type { SyncRun, SyncRunAccount } from '../../../api/syncLogs'
import { accountNote, describeWindow, runHeadline, runVerdict, windowDays } from './syncRunSummary'

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
    balance_drift: [],
    refused_anchors: [],
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
    change_batch_id: null,
    undone_at: null,
    created_at: '2026-09-16T01:00:00Z',
    ...over,
  }
}

const DRIFT = {
  account_id: 'a1',
  account_name: 'Harborstone Checking',
  bank_balance: '8213.5500',
  ledger_cleared_balance: '9453.7200',
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

  it('calls an undone run undone, whatever it did', () => {
    expect(runVerdict(run({ imported: 28, undone_at: '2026-09-18T00:30:00Z' }))).toBe('undone')
  })

  it('counts an adoption as work, not quiet', () => {
    expect(runVerdict(run({ adopted: 277 }))).toBe('worked')
  })

  it('calls a run that left a reconciled account off from the bank broken', () => {
    // Imported 28 and reported success, with 24 rows still missing.
    expect(runVerdict(run({ imported: 28, balance_drift: [DRIFT] }))).toBe('broken')
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

  it('leads with the gap when the ledger is off from the bank', () => {
    expect(runHeadline(run({ imported: 28, balance_drift: [DRIFT] }))).toContain(
      'off from the bank by 1,240.17'
    )
  })
})

describe('describeWindow', () => {
  it('names the start date, which is where a gap shows', () => {
    // The run that missed 24 rows posted on the 8th and 9th asked from the 11th.
    const text = describeWindow(
      run({ window_start: '2026-09-11T12:00:00Z', created_at: '2026-09-16T12:00:00Z' })
    )
    expect(text).toMatch(/Sep 11 → now \(5 days\)/)
  })

  it('is null when no window was recorded', () => {
    expect(describeWindow(run())).toBeNull()
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
      bank_balance: null,
      ledger_cleared_balance: null,
      balance_agrees: null,
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

  it('says when the ledger did not match the bank', () => {
    expect(accountNote(account({ balance_agrees: false }))).toContain('does not match')
  })

  it('stays quiet when they agreed', () => {
    expect(accountNote(account({ balance_agrees: true }))).toBeNull()
  })

  it('stays quiet when one of the figures was unknown', () => {
    // Null is not a disagreement. Treating it as one would warn on every
    // account whose bank reported no balance.
    expect(accountNote(account({ balance_agrees: null }))).toBeNull()
  })

  it('says nothing about an ordinary account', () => {
    expect(accountNote(account())).toBeNull()
  })
})

describe('a refused opening balance', () => {
  // A first sync that would have left a liability holding money. The one
  // outcome the drift line structurally cannot report, because an anchor is
  // the row that defines drift to be zero — the check reads its own output.
  const REFUSAL =
    'Sapphire Visa: the bank reports 2,690.00 on an account that owes money, so no opening ' +
    'balance was written against its register of -200.00. This usually means the feed reports ' +
    'debts as positive — reconcile the account or check the sign of its imported rows.'

  it('is broken, not quiet', () => {
    expect(runVerdict(run({ refused_anchors: [REFUSAL] }))).toBe('broken')
  })

  it('shows the server sentence whole, so the account is named', () => {
    const headline = runHeadline(run({ refused_anchors: [REFUSAL] }))
    expect(headline).toContain('Sapphire Visa')
    expect(headline).toContain('reconcile')
  })

  it('counts them when several accounts were refused', () => {
    expect(runHeadline(run({ refused_anchors: [REFUSAL, REFUSAL] }))).toBe(
      '2 accounts could not be given an opening balance'
    )
  })

  it('outranks drift, which it would otherwise hide', () => {
    const headline = runHeadline(run({ refused_anchors: [REFUSAL], balance_drift: [DRIFT] }))
    expect(headline).toContain('Sapphire Visa')
  })

  it('leaves an ordinary run alone', () => {
    expect(runVerdict(run({ imported: 3, refused_anchors: [] }))).toBe('worked')
  })
})
