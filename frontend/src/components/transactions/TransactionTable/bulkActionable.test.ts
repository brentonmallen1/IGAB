import { describe, expect, it } from 'vitest'
import { isLocked, isWholeRow, mayActOnAsRow, mayActOnInBulk } from './bulkActionable'
import type { ClearedStatus } from '../../../types'

const row = (cleared: ClearedStatus, parent: string | null = null) => ({
  cleared,
  parent_transaction_id: parent,
})

describe('bulkActionable', () => {
  it('locks reconciled rows and nothing else', () => {
    expect(isLocked(row('reconciled'))).toBe(true)
    for (const c of ['uncleared', 'cleared', 'pending'] as const)
      expect(isLocked(row(c))).toBe(false)
  })

  it('bulk delete, approve and select-all skip a reconciled row', () => {
    expect(mayActOnInBulk(row('reconciled'))).toBe(false)
    expect(mayActOnInBulk(row('cleared'))).toBe(true)
  })

  // The one difference between the copies: duplicate and the single-row Edit
  // also refused split lines; delete, approve and select-all never did.
  it('duplicate and single-row Edit also skip a split line, which bulk actions take', () => {
    const line = row('cleared', 'parent-1')
    expect(mayActOnInBulk(line)).toBe(true)
    expect(mayActOnAsRow(line)).toBe(false)
    expect(mayActOnAsRow(row('cleared'))).toBe(true)
    expect(mayActOnAsRow(row('reconciled'))).toBe(false)
  })

  // Make Repeating copies a row's terms and changes nothing on it, so a
  // reconciled row may become a schedule; a split line still may not.
  it('Make Repeating asks only for a whole row, reconciled or not', () => {
    expect(isWholeRow(row('reconciled'))).toBe(true)
    expect(isWholeRow(row('cleared', 'parent-1'))).toBe(false)
  })
})
