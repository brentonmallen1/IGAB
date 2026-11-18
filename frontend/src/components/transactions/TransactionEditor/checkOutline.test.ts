import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { stripComments, topLevelRules } from '../../../test-utils/cssRules'

/**
 * A receipt check outlines the amount box in the warning colour, and the
 * Outflow / Inflow boxes also wear their direction as a border. Both set
 * `border-color` on the same input, so which one shows is decided by the
 * cascade — and the check must win: it is the more urgent signal. It wins
 * by specificity, not by sitting later in the file, so a reordering cannot
 * hand the box back to red or green. jsdom has no cascade worth trusting;
 * this reads the stylesheet's contract instead.
 */

const CSS = stripComments(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'TransactionEditor.css'), 'utf8')
)

/** (ids, classes + pseudo-classes, types) for the simple selectors used here. */
function specificity(selector: string): [number, number, number] {
  const ids = (selector.match(/#[\w-]+/g) ?? []).length
  // `:not(x)` counts as its argument, which the pseudo-class scan below picks up.
  const plain = selector.replace(/:not\(/g, '(')
  const classes = (plain.match(/\.[\w-]+|:[\w-]+|\[[^\]]+\]/g) ?? []).length
  const types = (plain.replace(/[.:#][\w-]+|\[[^\]]+\]/g, '').match(/[a-z]+/gi) ?? []).length
  return [ids, classes, types]
}

const outranks = (a: [number, number, number], b: [number, number, number]) =>
  a[0] !== b[0] ? a[0] > b[0] : a[1] !== b[1] ? a[1] > b[1] : a[2] > b[2]

/** Every selector that sets border-color on an editor input, by rule body. */
function borderSelectors(): Array<{ selector: string; body: string }> {
  return topLevelRules(CSS).flatMap(([sel, body]) =>
    /border-color/.test(body) && /txn-editor__input/.test(sel)
      ? sel.split(',').map((s) => ({ selector: s.trim(), body }))
      : []
  )
}

describe('the receipt-check outline on an amount box', () => {
  const check = borderSelectors().find(
    (r) => r.selector.includes('txn-editor__input--check') && /--color-warning/.test(r.body)
  )

  it('is drawn in the warning colour', () => {
    expect(check).toBeDefined()
  })

  it('outranks the direction border on an unfocused box', () => {
    const direction = borderSelectors().filter(
      (r) =>
        /txn-editor__field--(outflow|inflow)/.test(r.selector) &&
        !r.selector.includes(':focus') &&
        !r.selector.includes('--check')
    )
    expect(direction.length).toBeGreaterThan(0)
    for (const rule of direction) {
      expect(
        outranks(specificity(check!.selector), specificity(rule.selector)),
        `${check!.selector} vs ${rule.selector}`
      ).toBe(true)
    }
  })
})
