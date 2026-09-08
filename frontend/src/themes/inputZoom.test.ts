import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../test-utils/cssRules'

/**
 * The 16px input floor lives once.
 *
 * iOS zooms the viewport into any focused control under 16px, and the app's
 * viewport tokens deliberately freeze while zoomed — one undersized input
 * made a whole page look broken. base.css floors every input, select and
 * textarea on a touch phone. Six components had written the same 16px in
 * their own phone blocks before that rule existed; each was shadowed by it
 * and free to say anything. This holds the count at one.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return cssFiles(full)
    return full.endsWith('.css') ? [full] : []
  })
}

describe('the iOS focus-zoom floor', () => {
  const base = rulesWithContext(stripComments(readFileSync(join(SRC, 'themes/base.css'), 'utf8')))

  it('is declared once, in base.css, for every text control on a touch phone', () => {
    const floor = base.find(
      (r) =>
        r.atRules.some((a) => /hover:\s*none/.test(a) && /max-width:\s*768px/.test(a)) &&
        /font-size:\s*max\(16px/.test(r.body)
    )
    expect(floor).toBeDefined()
    for (const tag of ['input', 'select', 'textarea']) {
      expect(floor!.selector.split(',').map((s) => s.trim())).toContain(tag)
    }
  })

  it('is written nowhere else', () => {
    const copies: string[] = []
    for (const file of cssFiles(SRC)) {
      const rel = relative(SRC, file)
      if (rel === 'themes/base.css') continue
      for (const r of rulesWithContext(stripComments(readFileSync(file, 'utf8')))) {
        if (r.atRules.some((a) => /max-width/.test(a)) && /font-size:\s*16px/.test(r.body)) {
          copies.push(`${rel}: ${r.selector.trim()}`)
        }
      }
    }
    expect(copies, 'base.css already floors this control at 16px on phones').toEqual([])
  })
})
