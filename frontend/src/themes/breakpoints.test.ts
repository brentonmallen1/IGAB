import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { stripComments } from '../test-utils/cssRules'

/**
 * One phone breakpoint.
 *
 * `useIsMobile()` is 768px and every component that branches in JS agrees
 * with it; the stylesheets did not — 640, 620, 700, 720, 600 and 900 all
 * existed, twelve files on 640 alone. Each fired at 390px so nothing was
 * visibly wrong, which is exactly how a value drifts: a rule written at 640
 * stops matching a 700px foldable that the JS still calls mobile, and the
 * page half-adapts. Every width query is 768 now, and the one touch test is
 * `(hover: none)`, which `useIsTouch()` also asks.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

/** Queries that are not the phone breakpoint, each with its reason. */
const ALLOWED: Record<string, string> = {
  'themes/base.css @media (max-width: 900px) and (max-height: 500px)':
    'a phone in landscape — keyed on the short axis, the width only rules out tablets',
  'components/reports/OverviewReport.css @media (min-width: 1100px)':
    'a desktop-only two-column layout above the sidebar breakpoint',
  'components/budget/CategoryRow.css @media (min-width: 769px)': 'the complement of 768',
  'components/budget/CategoryRow/CategoryRow.css @media (min-width: 769px)':
    'the complement of 768',
  'components/budget/budgetGrid.css @media (min-width: 769px)': 'the complement of 768',
  'components/budget/CategoryGroupRow/CategoryGroupRow.css @media (min-width: 769px)':
    'the complement of 768',
  'components/transactions/TransactionRow/TransactionRow.css @media (min-width: 769px)':
    'the complement of 768',
}

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return cssFiles(full)
    return full.endsWith('.css') ? [full] : []
  })
}

function widthQueries(): Array<{ file: string; query: string }> {
  const found: Array<{ file: string; query: string }> = []
  for (const file of cssFiles(SRC)) {
    const src = stripComments(readFileSync(file, 'utf8'))
    for (const m of src.matchAll(/@media[^{]*\((?:min|max)-width[^{]*/g)) {
      found.push({ file: relative(SRC, file), query: m[0].trim() })
    }
  }
  return found
}

describe('the phone breakpoint is 768px everywhere', () => {
  const queries = widthQueries()

  // The width a query names, whatever else it combines with — the 16px input
  // floor is `(hover: none) and (max-width: 768px)` and is still the one
  // breakpoint.
  const width = (q: string) => Number(q.match(/(?:min|max)-width:\s*(\d+)px/)?.[1])
  const isPhone = (q: string) => /max-width/.test(q) && width(q) === 768

  it('finds the breakpoint (a green run must mean something)', () => {
    expect(queries.filter((q) => isPhone(q.query)).length).toBeGreaterThan(40)
  })

  it('names no other width', () => {
    const strays = queries
      .filter((q) => !isPhone(q.query))
      .filter((q) => !(`${q.file} ${q.query}` in ALLOWED))
      .map((q) => `${q.file}: ${q.query}`)
    expect(
      strays,
      `${strays.join('\n')}\nUse 768px (useIsMobile's width), or add it to ALLOWED with its reason.`
    ).toEqual([])
  })

  it('keeps every allowance honest', () => {
    for (const key of Object.keys(ALLOWED)) {
      const [file, ...rest] = key.split(' ')
      const query = rest.join(' ')
      // Only entries that name a file that exists must still match; the
      // CategoryRow entries cover two historical paths, one of which is real.
      const present = queries.some((q) => q.file === file && q.query === query)
      const exists = cssFiles(SRC).some((f) => relative(SRC, f) === file)
      if (exists) expect(present, `${key}: ${ALLOWED[key]} — stale entry`).toBe(true)
    }
  })

  it('uses (hover: none) as the one touch test, never (pointer: coarse)', () => {
    const coarse = cssFiles(SRC).filter((f) =>
      /pointer:\s*coarse/.test(stripComments(readFileSync(f, 'utf8')))
    )
    expect(coarse.map((f) => relative(SRC, f))).toEqual([])
  })
})
