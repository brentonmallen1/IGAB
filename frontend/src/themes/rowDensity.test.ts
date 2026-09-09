import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../test-utils/cssRules'
import { BUDGET_ROW_MODES } from '../stores/uiStore'

/**
 * Three modes in the picker means three renders on every screen.
 *
 * The `--dense` rules were scoped to `(min-width: 769px)`, so a phone drew
 * Compact and Dense identically and the control offered a choice that did
 * nothing. The row component's own branching is only two-way — everything
 * that is not `expanded` gets the dot instead of the badge — so the third
 * mode exists in CSS or it does not exist at all.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')
const rules = rulesWithContext(
  stripComments(readFileSync(join(SRC, 'components/budget/CategoryRow/CategoryRow.css'), 'utf8'))
)
const denseIn = (test: (a: string) => boolean) =>
  rules.filter((r) => r.selector.includes('.category-row--dense') && r.atRules.some(test))

describe('row density', () => {
  it('offers exactly the three modes these rules answer for', () => {
    expect(BUDGET_ROW_MODES.map((m) => m.value)).toEqual(['expanded', 'compact', 'dense'])
  })

  it('makes Dense shorter than Compact on a phone', () => {
    const phone = denseIn((a) => /max-width:\s*768px/.test(a))
    expect(phone.length, 'no --dense rules in the phone block').toBeGreaterThan(0)
    const shortens = phone.some((r) => /display:\s*none/.test(r.body) || /min-height/.test(r.body))
    expect(shortens, 'Dense must remove or shrink something a phone draws').toBe(true)
  })

  it('and on the desktop grid too', () => {
    expect(denseIn((a) => /min-width:\s*769px/.test(a)).length).toBeGreaterThan(0)
  })

  it('never shrinks a phone row below the tap floor', () => {
    // Dense means shorter rows, never harder targets: it may set min-height,
    // but only to the token every other touch control is held to.
    for (const r of denseIn((a) => /max-width:\s*768px/.test(a))) {
      const min = r.body.match(/min-height:\s*([^;]+)/)
      if (min) expect(min[1].trim()).toBe('var(--tap-min)')
    }
  })
})
