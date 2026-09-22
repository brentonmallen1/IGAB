/**
 * A merged-in receipt vanished from the register.
 *
 * Merging a plain row with one holding an image moves the image onto the
 * survivor. The editor's panel showed it; the register's indicator kept
 * saying the row had none, because the bulk map that feeds the indicator was
 * never staled. Undo refreshed it — so taking the merge back fixed the icon
 * that doing the merge had broken.
 *
 * The pair of caches was spelled four times and missing from the fifth place.
 * These pin the one list and pin that every path runs it.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { invalidateAfterAttachmentChange } from './invalidateAfterAttachmentChange'
import { invalidateAfterTransactionChange } from './invalidateAfterTransactionChange'
import { invalidateAfterUndo } from './changes'
import { ROOT } from './queryKeys'

function keysFrom(run: (qc: QueryClient) => void): string[] {
  const qc = new QueryClient()
  const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined)
  vi.spyOn(qc, 'refetchQueries').mockResolvedValue(undefined)
  run(qc)
  return spy.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
}

const CHECK = JSON.stringify([ROOT.attachmentCheck])

describe('invalidateAfterAttachmentChange', () => {
  it('stales the editor panel and the register indicator, exactly', () => {
    const keys = keysFrom((qc) => invalidateAfterAttachmentChange(qc, ['t1']))
    expect(keys.sort()).toEqual([CHECK, JSON.stringify([ROOT.attachments, 't1'])].sort())
  })

  it('scopes the panel per transaction, and stales the indicator at its root', () => {
    // The indicator's key carries the register's whole id list, so there is
    // no per-transaction entry to target — only the root reaches it.
    const keys = keysFrom((qc) => invalidateAfterAttachmentChange(qc, ['t1', 't2']))
    expect(keys).toContain(JSON.stringify([ROOT.attachments, 't1']))
    expect(keys).toContain(JSON.stringify([ROOT.attachments, 't2']))
    expect(keys).toContain(CHECK)
    expect(keys).not.toContain(JSON.stringify([ROOT.attachments]))
  })

  it('falls back to every panel when the caller cannot name the rows', () => {
    const keys = keysFrom((qc) => invalidateAfterAttachmentChange(qc))
    expect(keys.sort()).toEqual([CHECK, JSON.stringify([ROOT.attachments])].sort())
  })
})

describe('the paths that move a receipt', () => {
  it('a transaction change stales the indicator — this is the merge bug', () => {
    // Merge runs invalidateAfterTransactionChange and nothing else. Without
    // the indicator here, the survivor's row kept the cached `false`.
    const keys = keysFrom((qc) =>
      invalidateAfterTransactionChange(qc, {
        budgetId: 'b1',
        accountId: 'a1',
        transactionIds: ['survivor', 'loser'],
      })
    )
    expect(keys).toContain(CHECK)
    expect(keys).toContain(JSON.stringify([ROOT.attachments, 'survivor']))
    expect(keys).toContain(JSON.stringify([ROOT.attachments, 'loser']))
  })

  it('undo stales the same pair — it moves receipts back off the survivor', () => {
    const keys = keysFrom((qc) => invalidateAfterUndo(qc, 'b1'))
    expect(keys).toContain(CHECK)
    expect(keys).toContain(JSON.stringify([ROOT.attachments]))
  })
})
