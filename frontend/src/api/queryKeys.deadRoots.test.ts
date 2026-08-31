/**
 * A root nothing answers to cannot survive in ROOT.
 *
 * `['category-transactions']` was invalidated at twelve sites and was never a
 * query key anywhere. It refreshed nothing, silently, for as long as it
 * existed — and the symptom users reported was "I had to reload the page".
 * `['netWorth']` and `['duplicatePayees']` were the same shape, and an earlier
 * one (`['category-groups']` for `categoryGroups`) is recorded in a comment in
 * `changes.ts` rather than by anything that fails.
 *
 * So this scans the source the way `themes/contrast.test.ts` scans the
 * stylesheets: every root in ROOT must appear in at least one real query, and
 * no literal root string may appear in a key position outside this module.
 * Together those make the mismatch unrepresentable rather than merely
 * discouraged.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { ROOT } from './queryKeys'

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return sources(full)
    if (!/\.tsx?$/.test(entry) || entry.includes('.test.')) return []
    if (entry === 'queryKeys.ts') return []
    return [full]
  })
}

const FILES = sources(SRC)
const CODE = FILES.map((f) => readFileSync(f, 'utf8')).join('\n')

/** Roots a real query answers to.
 *
 * `queryKey:` alone is not enough — `invalidateQueries({ queryKey: [...] })`
 * uses the same property, so counting those would let every dead root vouch
 * for itself. Only a `queryKey:` that is NOT inside an invalidate/refetch/
 * remove/cancel/setData call counts, plus the module-level key factories. */
const CACHE_CALL = /(?:invalidate|refetch|remove|cancel|prefetch|fetch|set|get)Quer/
const QUERIED = new Set([
  ...[...CODE.matchAll(/queryKey:\s*\[\s*ROOT\.(\w+)/g)]
    .filter((m) => !CACHE_CALL.test(CODE.slice(Math.max(0, m.index - 160), m.index)))
    .map((m) => m[1]),
  ...[...CODE.matchAll(/=>\s*\[\s*ROOT\.(\w+)/g)].map((m) => m[1]),
  // Key factories: `all: [ROOT.changes] as const`, spread into real keys.
  ...[...CODE.matchAll(/^\s*\w+:\s*\[\s*ROOT\.(\w+)\]\s*as const/gm)].map((m) => m[1]),
])

describe('query key roots', () => {
  it('spells no root as a bare string outside this module', () => {
    const offenders: string[] = []
    for (const file of FILES) {
      const text = readFileSync(file, 'utf8')
      for (const m of text.matchAll(/queryKey:\s*\[\s*'([\w-]+)'/g)) {
        offenders.push(`${file.slice(SRC.length)}: ['${m[1]}']`)
      }
    }
    expect(offenders, 'a key spelled here cannot be kept in step with ROOT').toEqual([])
  })

  it('carries no root that no query answers to', () => {
    // Invalidation-only roots are the bug. A root worth having is one some
    // useQuery — or a key factory — actually builds a key from.
    const dead = Object.keys(ROOT).filter((name) => !QUERIED.has(name))
    expect(dead, 'invalidating these refreshes nothing').toEqual([])
  })

  it('has no two names for one root string', () => {
    const values = Object.values(ROOT)
    expect(new Set(values).size, `duplicate root strings in ROOT: ${values}`).toBe(values.length)
  })
})
