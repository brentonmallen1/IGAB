import { describe, expect, it } from 'vitest'
import { selectAllStep } from './selectAll'
import type { ClearedStatus } from '../../../types'

const row = (id: string, cleared: ClearedStatus) => ({ id, cleared })
const ROWS = [
  row('open-1', 'uncleared'),
  row('locked-1', 'reconciled'),
  row('open-2', 'cleared'),
  row('pending-1', 'pending'),
  row('locked-2', 'reconciled'),
]
const UNLOCKED = ['open-1', 'open-2', 'pending-1']
const EVERY = ROWS.map((r) => r.id)
const ids = (s: Set<string>) => [...s].sort()

describe('selectAllStep', () => {
  it('reconciled rows are locked, so the first click leaves them out', () => {
    expect(ids(selectAllStep(ROWS, new Set()))).toEqual([...UNLOCKED].sort())
  })

  it('a partial selection also steps to every unlocked row, dropping nothing it held', () => {
    expect(ids(selectAllStep(ROWS, new Set(['open-1'])))).toEqual([...UNLOCKED].sort())
  })

  it('every unlocked row selected → the second click adds the reconciled rows', () => {
    expect(ids(selectAllStep(ROWS, new Set(UNLOCKED)))).toEqual([...EVERY].sort())
  })

  it('the unlocked rows plus a hand-picked locked row still steps to everything', () => {
    expect(ids(selectAllStep(ROWS, new Set([...UNLOCKED, 'locked-1'])))).toEqual([...EVERY].sort())
  })

  it('every row selected → the third click clears', () => {
    expect(selectAllStep(ROWS, new Set(EVERY)).size).toBe(0)
  })

  it('a register of reconciled rows only selects them all on the first click', () => {
    const locked = [row('locked-1', 'reconciled'), row('locked-2', 'reconciled')]
    expect(ids(selectAllStep(locked, new Set()))).toEqual(['locked-1', 'locked-2'])
    expect(selectAllStep(locked, new Set(['locked-1', 'locked-2'])).size).toBe(0)
  })

  it('a register of unlocked rows goes straight from all to none', () => {
    const open = [row('open-1', 'uncleared'), row('open-2', 'cleared')]
    expect(ids(selectAllStep(open, new Set()))).toEqual(['open-1', 'open-2'])
    expect(selectAllStep(open, new Set(['open-1', 'open-2'])).size).toBe(0)
  })

  it('an empty register selects nothing', () => {
    expect(selectAllStep([], new Set()).size).toBe(0)
  })
})
