/**
 * `types/index.ts` declared five report interfaces TWICE, byte for byte —
 * `SpendingTrendSeries`, `SpendingTrendsReport`, `IncomeSource`,
 * `IncomeBySourceReport` and `CategoryHistoryReport`.
 *
 * TypeScript's declaration merging makes that legal and silent, so nothing
 * caught it: not `tsc`, not eslint, not review. It is only harmless while the
 * copies stay identical — add a field to one and the merged interface quietly
 * gains it everywhere, and give a field a different type and the error lands
 * on a line nobody edited.
 *
 * This file is the mechanism. A comment asking the next reader to check for
 * duplicates is not one.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('types/index.ts', () => {
  const src = fs.readFileSync(path.resolve(__dirname, 'index.ts'), 'utf8')

  it('declares each interface exactly once', () => {
    const seen = new Map<string, number>()
    for (const m of src.matchAll(/^export interface (\w+)/gm)) {
      seen.set(m[1], (seen.get(m[1]) ?? 0) + 1)
    }
    const duplicated = [...seen.entries()].filter(([, n]) => n > 1).map(([name]) => name)
    expect(duplicated).toEqual([])
  })

  it('finds the interfaces at all, so the scan cannot pass by finding nothing', () => {
    const count = [...src.matchAll(/^export interface (\w+)/gm)].length
    expect(count).toBeGreaterThan(50)
  })
})
