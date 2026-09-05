/**
 * "Money moved" had seven spellings and seven different cache lists.
 *
 * The one that mattered was the shortest: `invalidateAfterUndo` refreshed the
 * grid and nothing else, so undoing a bulk assign left the TBA hero's strategy
 * amounts, the overspent pill, the preview table and the month's move list
 * still showing the operation that had just been taken back. This pins the
 * single list and, below, pins that undo actually uses it — the whole point of
 * consolidating.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { invalidateAfterMoneyMove } from './invalidateAfterMoneyMove'
import { invalidateAfterUndo } from './changes'
import { ROOT } from './queryKeys'

function keysFrom(run: (qc: QueryClient) => void): string[] {
  const qc = new QueryClient()
  const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined)
  vi.spyOn(qc, 'refetchQueries').mockResolvedValue(undefined)
  run(qc)
  return spy.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
}

const MONEY_KEYS = [
  [ROOT.budgetMonth, 'b1'],
  [ROOT.budgetMoves, 'b1'],
  [ROOT.assignStrategies, 'b1'],
  [ROOT.assignPreview, 'b1'],
  [ROOT.coverOverspentPreview, 'b1'],
  [ROOT.categoryHistoryBatch, 'b1'],
].map((k) => JSON.stringify(k))

describe('invalidateAfterMoneyMove', () => {
  it('stales every cache an assignment changes — the whole list, exactly', () => {
    const keys = keysFrom((qc) => invalidateAfterMoneyMove(qc, 'b1'))
    expect(keys.sort()).toEqual([...MONEY_KEYS].sort())
  })

  it('does not scope to a month', () => {
    // Assignments ripple forward: a July assignment moves every later month's
    // available and every month's Ready to Assign. Four of the old copies
    // pinned `[root, budgetId, month]`, which staled one month of many.
    for (const key of keysFrom((qc) => invalidateAfterMoneyMove(qc, 'b1'))) {
      expect(JSON.parse(key)).toHaveLength(2)
    }
  })
})

describe('invalidateAfterUndo', () => {
  it('stales the money caches too — undo has to match apply', () => {
    // The reported bug: applying a bulk assign refreshed six keys, undoing it
    // refreshed one, so the hero kept the undone operation's figures.
    const keys = keysFrom((qc) => invalidateAfterUndo(qc, 'b1'))
    for (const key of MONEY_KEYS) {
      expect(keys).toContain(key)
    }
  })
})
