/**
 * Four cleared states and one modifier, each told apart by something the
 * register can afford.
 *
 * The design was chosen in the row lab against all 40 palettes at once. What
 * these pin is the part a stylesheet edit can silently undo: which signal each
 * state owns, that the cheap signals stay cheap, and the source order the
 * modifier depends on.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { stripComments, topLevelRules } from '../../../test-utils/cssRules'

const HERE = dirname(fileURLToPath(import.meta.url))
const CSS = readFileSync(join(HERE, 'TransactionRow.css'), 'utf8')
const BASE = readFileSync(join(HERE, '../../../themes/base.css'), 'utf8')
const RULES = [...topLevelRules(stripComments(CSS))]
const at = (sel: string) => {
  const hit = RULES.find(([s]) => s.trim() === sel)
  expect(hit, `${sel} is missing`).toBeTruthy()
  return hit![1]
}
const orderOf = (sel: string) => RULES.findIndex(([s]) => s.trim() === sel)

describe('each state owns a signal', () => {
  it('uncleared is a neutral marker, not a colour', () => {
    expect(at('.transaction-row.uncleared')).toContain('--row-marker: var(--edge-strong)')
  })

  it('cleared is weight, which costs no contrast at all', () => {
    // WCAG has no weight term, and heavier text at 13px is easier to read, not
    // harder — the only lever that improves both axes at once.
    expect(at('.transaction-row.cleared')).toContain('font-weight: 600')
  })

  it('reconciled recedes by texture and by giving up its amount colour', () => {
    const r = at('.transaction-row.reconciled')
    expect(r).toContain('repeating-linear-gradient')
    expect(r).toContain('var(--text-muted)')
    // Not by fading: opacity composites text toward the ground and would undo
    // the contrast the rest of this file is buying.
    expect(r).not.toContain('opacity')
    expect(
      at('.transaction-row.reconciled .txn-outflow,\n.transaction-row.reconciled .txn-inflow')
    ).toContain('color: inherit')
  })

  it('pending is the one state that spends contrast, and it is recorded', () => {
    expect(at('.transaction-row.pending')).toContain('var(--row-pending-bg)')
    expect(BASE).toMatch(/--row-pending-bg:\s*color-mix\(in srgb, var\(--text-primary\) 13%/)
    // The cost is not silent: every theme that drops below AA is named, with
    // the floor it measures today, in contrast.test.ts.
    const contrast = readFileSync(join(HERE, '../../../themes/contrast.test.ts'), 'utf8')
    expect(contrast).toContain('ROW_STATE_AA_EXCEPTIONS')
  })
})

describe('unapproved replaces, it does not layer', () => {
  it('no longer fades the row', () => {
    // It was `opacity: 0.65`. Fading composites text toward the ground, so a
    // ratio measured on a token is not the ratio the row renders at: at 0.65
    // the register's muted text and its coloured amounts failed AA in 40 of 40.
    expect(at('.transaction-row.unapproved')).not.toContain('opacity')
  })

  it('undoes every property the states above it set', () => {
    // This is the pairing that matters. A row that is unapproved AND cleared
    // must not be bold: "waiting on a person" outranks "the bank agreed", so
    // the row wears the unapproved treatment alone. Each reset below answers
    // exactly one state, and a state that gains a property without gaining a
    // reset here goes back to layering without anything saying so.
    const mod = at('.transaction-row.unapproved')
    expect(mod, 'cleared sets font-weight: 600').toContain('font-weight: 400')
    expect(mod, 'pending sets background-color').toContain('background-color: transparent')
    expect(mod, 'reconciled sets background-image').toContain('background-image: none')
    expect(mod, 'reconciled sets color').toContain('color: var(--text-primary)')
  })

  it('resets exactly the properties the states declare, and no fewer', () => {
    // Derived from the stylesheet rather than listed by hand, so a new
    // property on any state fails here until it is answered above.
    const owned = new Set<string>()
    for (const sel of [
      '.transaction-row.cleared',
      '.transaction-row.reconciled',
      '.transaction-row.pending',
    ]) {
      for (const decl of at(sel).split(';')) {
        const k = decl.split(':')[0].trim()
        if (k && !k.startsWith('--') && !k.startsWith('.')) owned.add(k)
      }
    }
    const mod = at('.transaction-row.unapproved')
    for (const prop of owned) {
      expect(mod, `.unapproved must reset ${prop}`).toContain(prop + ':')
    }
  })

  it('takes the amount colour back from reconciled', () => {
    expect(at('.transaction-row.unapproved .txn-outflow')).toContain('var(--color-negative)')
    expect(at('.transaction-row.unapproved .txn-inflow')).toContain('var(--color-positive)')
  })

  it('comes after every state it overrides', () => {
    // All of these are two classes, so specificity ties and source order is
    // the entire decision. Move this rule up and unapproved stops winning.
    const mod = orderOf('.transaction-row.unapproved')
    for (const sel of [
      '.transaction-row.uncleared',
      '.transaction-row.cleared',
      '.transaction-row.reconciled',
      '.transaction-row.pending',
    ]) {
      expect(orderOf(sel), `${sel} must precede .unapproved`).toBeLessThan(mod)
    }
  })
})

describe('the row marker', () => {
  it('is one declaration that state only recolours', () => {
    const setters = RULES.filter(
      ([sel, body]) => sel.includes('.transaction-row') && /(^|[;{\s])box-shadow\s*:/.test(body)
    )
    expect(setters.map(([s]) => s.trim())).toEqual(['.transaction-row'])
    expect(at('.transaction-row')).toContain('var(--row-marker)')
  })
})
