import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { stripComments } from '../test-utils/cssRules'

/**
 * The bottom edge of the phone shell, pinned as source.
 *
 * jsdom has no safe-area insets, so every arrangement of these declarations
 * agrees there and disagrees only on a phone with a home indicator. What can
 * be held here is the contract each declaration states:
 *
 *   - `--nav-h` includes the inset, so everything positioned against the nav
 *     (toasts, the selection bar, the reconcile bar) lifts with it and needs
 *     no safe-bottom term of its own;
 *   - the nav pads its own bottom by the inset, so the tabs sit above the
 *     indicator while the bar's background reaches the screen edge;
 *   - nothing adds `--safe-bottom` ON TOP of `--nav-h`, which would double it.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (rel: string) => stripComments(readFileSync(join(SRC, rel), 'utf8'))

describe('the bottom nav owns the home-indicator inset', () => {
  const base = read('themes/base.css')
  const mobileNavH = base.match(
    /@media \(max-width: 768px\)\s*{\s*:root\s*{[^}]*--nav-h:\s*([^;]+);/
  )?.[1]

  it('declares --nav-h for phones', () => {
    expect(mobileNavH).toBeDefined()
  })

  it('folds the inset into --nav-h', () => {
    expect(mobileNavH).toContain('var(--bottom-nav-height)')
    expect(mobileNavH).toContain('var(--safe-bottom)')
  })

  it('collapses --nav-h to 0 while the keyboard is up', () => {
    expect(base).toMatch(/html\[data-keyboard="open"\]\s*{\s*--nav-h:\s*0px;/)
  })

  it('pads the nav by the inset so the tabs sit above the indicator', () => {
    const nav = read('components/layout/BottomNav/BottomNav.css')
    const rule = nav.match(/\.bottom-nav\s*{[^}]*}/g)?.find((r) => r.includes('padding-bottom'))
    expect(rule).toBeDefined()
    expect(rule).toMatch(/padding-bottom:\s*var\(--safe-bottom\)/)
    expect(rule).toMatch(/box-sizing:\s*border-box/)
  })
})

describe('nothing stacks --safe-bottom on top of --nav-h', () => {
  // Both terms in one expression joined by `+` is the double count.
  const doubled =
    /var\(--nav-h\)\s*\+\s*var\(--safe-bottom\)|var\(--safe-bottom\)\s*\+\s*var\(--nav-h\)/

  it.each([
    'App.tsx',
    'components/common/FloatingSelectionBar/FloatingSelectionBar.css',
    'components/accounts/ReconcileStatusBar.css',
  ])('%s', (rel) => {
    expect(read(rel)).not.toMatch(doubled)
  })
})
