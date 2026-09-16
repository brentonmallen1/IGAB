/**
 * What a sync run tells the user in one line.
 *
 * The case that matters: a re-linked bank account stopped matching anything,
 * and this line read "Imported 0, skipped 586" — identical to a quiet morning
 * with nothing new. Nine days passed before anyone looked closer.
 */
import { describe, expect, it } from 'vitest'

import { formatSyncSummary, type ConnectionSyncOutcome, type SyncAllResult } from './simplefin'

function connection(over: Partial<ConnectionSyncOutcome> = {}): ConnectionSyncOutcome {
  return {
    connection_id: 'c1',
    imported: 0,
    skipped: 0,
    adopted: 0,
    error: null,
    orphaned_links: [],
    bank_errors: [],
    ...over,
  }
}

function result(over: Partial<SyncAllResult> = {}): SyncAllResult {
  return {
    imported: 0,
    skipped: 0,
    matched: 0,
    adopted: 0,
    review_queued: 0,
    cleared: 0,
    removed_pending: 0,
    connections: [connection()],
    ...over,
  }
}

describe('formatSyncSummary', () => {
  it('leads with a broken bank link instead of a skip count', () => {
    const summary = formatSyncSummary(
      result({
        skipped: 586,
        skip_reasons: { foreign_account: 586 },
        connections: [
          connection({
            skipped: 586,
            orphaned_links: [
              {
                account_id: 'a1',
                account_name: 'Harborstone Checking',
                stored_simplefin_id: 'ACT-old',
                suggested_feed_id: 'ACT-new',
                suggested_feed_name: 'HARBORSTONE EVERYDAY CHECKING',
              },
            ],
          }),
        ],
      })
    )
    expect(summary).toContain('Harborstone Checking')
    expect(summary).toContain('relink')
    expect(summary).not.toMatch(/^Imported 0/)
  })

  it('names the count when several accounts are orphaned', () => {
    const orphan = (name: string) => ({
      account_id: name,
      account_name: name,
      stored_simplefin_id: 'ACT-old',
      suggested_feed_id: null,
      suggested_feed_name: null,
    })
    const summary = formatSyncSummary(
      result({
        connections: [
          connection({ orphaned_links: [orphan('Harborstone Checking'), orphan('Savings')] }),
        ],
      })
    )
    expect(summary).toContain('2 accounts')
  })

  it('surfaces an institution that needs re-authenticating', () => {
    const summary = formatSyncSummary(
      result({
        connections: [
          connection({
            bank_errors: [
              {
                code: 'con.auth',
                message: 'Connection to Harborstone may need attention. Auth required',
                connection_id: 'MBR-1',
              },
            ],
          }),
        ],
      })
    )
    expect(summary).toContain('re-authenticating')
  })

  it('ignores a capped-range notice, which is ours to fix and not the user’s', () => {
    const summary = formatSyncSummary(
      result({
        imported: 3,
        connections: [
          connection({
            imported: 3,
            bank_errors: [{ code: 'gen.api', message: 'range capped', connection_id: null }],
          }),
        ],
      })
    )
    expect(summary).toBe('Imported 3')
  })

  it('says nothing new, rather than skipped, when every row was already filed', () => {
    const summary = formatSyncSummary(
      result({ skipped: 512, skip_reasons: { already_posted: 512 } })
    )
    expect(summary).toBe('Imported 0, 512 already filed')
  })

  it('says whose rows they were when every skip was an unlinked account', () => {
    const summary = formatSyncSummary(
      result({ skipped: 40, skip_reasons: { foreign_account: 40 } })
    )
    expect(summary).toContain('unlinked accounts')
  })

  it('reports adopted rows so a re-link does not look like an import', () => {
    const summary = formatSyncSummary(result({ imported: 53, adopted: 277 }))
    expect(summary).toContain('re-linked 277 existing')
  })

  it('still counts failed connections', () => {
    const summary = formatSyncSummary(
      result({ imported: 2, connections: [connection({ error: 'rate limited' })] })
    )
    expect(summary).toContain('1 connection could not sync')
  })

  it('reports a mixed run without a skip clause when nothing was skipped', () => {
    const summary = formatSyncSummary(result({ imported: 4, matched: 2, cleared: 1 }))
    expect(summary).toBe('Imported 4, matched 2, cleared 1')
  })
})
