import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../../../test-utils/cssRules'

/**
 * The cards strip fits a phone.
 *
 * Each card is one line — name and word, a bar, the Set aside figure — that
 * opens in place. The old five-column table overflowed a 390pt screen and hid
 * Uncovered off the edge; this pins that the line and its opened detail work
 * at phone width, with touch-sized targets, and never push the page sideways.
 */
const css = stripComments(readFileSync(resolve(__dirname, 'CreditCardsSection.css'), 'utf8'))
const phone = rulesWithContext(css).filter((r) =>
  r.atRules.some((a) => a.includes('max-width: 768px'))
)
const rule = (sel: string) => phone.find((r) => r.selector.trim() === sel)?.body ?? ''
const base = (sel: string) =>
  rulesWithContext(css).find((r) => r.atRules.length === 0 && r.selector.trim() === sel)?.body ?? ''

describe('credit-cards strip on a phone', () => {
  it('makes the whole line a touch target', () => {
    expect(rule('.credit-cards__line')).toMatch(/min-height:\s*var\(--tap-min\)/)
  })

  it('keeps the name and its word, and narrows the bar rather than the figure', () => {
    expect(rule('.credit-cards__line')).toMatch(
      /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+44px\s+auto/
    )
  })

  it('lets the name shrink so the line never overflows', () => {
    // An .sr-only span escaping an unpositioned scroller once widened the
    // whole budget page; the name ellipses instead.
    expect(base('.credit-cards__line-name')).toMatch(/min-width:\s*0/)
    expect(base('.credit-cards__card-name')).toMatch(/text-overflow:\s*ellipsis/)
  })

  it('gives every action in the opened card a real touch target', () => {
    // Labelled buttons, not 12px icons with a title — a title is unreachable
    // on the installed iOS PWA, which is the app's mobile target.
    expect(rule('.credit-cards__action')).toMatch(/min-height:\s*var\(--tap-min\)/)
  })

  it('lets captions wrap instead of pushing the strip sideways', () => {
    const wrapping = phone.find((r) => r.selector.includes('.credit-cards__movement'))
    expect(wrapping?.body).toMatch(/white-space:\s*normal/)
  })
})
