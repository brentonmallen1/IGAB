import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments, topLevelRules } from '../../../test-utils/cssRules'

/**
 * The register row has ONE mobile card layout, and nothing outranks it.
 *
 * `.transaction-table--all-accounts .transaction-row` (0,2,0) declared a
 * ten-column desktop template at top level; the phone card template on
 * `.transaction-row` (0,1,0) lives in a media query, and media queries add no
 * specificity. So /transactions kept the desktop grid on phones while the
 * mobile cell placement still applied — every row scrambled and dragging
 * sideways. Read as source: jsdom resolves neither specificity nor media.
 */
const css = stripComments(readFileSync(resolve(__dirname, 'TransactionRow.css'), 'utf8'))

describe('the register row grid', () => {
  it('declares its columns at top level only on the bare row', () => {
    const declaring = topLevelRules(css)
      .filter(([, body]) => /grid-template-columns\s*:/.test(body))
      .map(([sel]) => sel.trim())
    expect(declaring).toEqual(['.transaction-row'])
  })

  it('scopes the all-accounts template to desktop widths', () => {
    const rule = rulesWithContext(css).find((r) =>
      r.selector.includes('.transaction-table--all-accounts .transaction-row')
    )
    expect(rule).toBeDefined()
    expect(rule!.atRules).toEqual(['@media (min-width: 769px)'])
  })

  it('has a phone card template', () => {
    const card = rulesWithContext(css).find(
      (r) =>
        r.selector.trim() === '.transaction-row' &&
        r.atRules.some((a) => a.includes('max-width: 768px')) &&
        /grid-template-columns/.test(r.body)
    )
    expect(card).toBeDefined()
  })
})

/**
 * The running balance is one more track, appended LAST, by redefining the
 * variable every register grid reads — never a template of its own. The
 * upcoming and split-line rows place their cells by column number, so a
 * track inserted mid-list, or a second track list typed out beside the
 * first, would leave them captioned by the wrong header.
 */
describe('the running-balance track', () => {
  const read = (path: string) => stripComments(readFileSync(resolve(__dirname, path), 'utf8'))
  const table = read('../TransactionTable/TransactionTable.css')
  const base = read('../../../themes/base.css')

  it('is the base tracks plus one, appended', () => {
    const rule = topLevelRules(table).find(([sel]) => sel.trim() === '.transaction-table--running')
    expect(rule).toBeDefined()
    expect(rule![1]).toMatch(
      /--register-cols\s*:\s*var\(--register-tracks\)\s+var\(--register-col-balance\)\s*;/
    )
  })

  it('leaves the base list defined once, as the tracks', () => {
    expect(base).toMatch(/--register-cols\s*:\s*var\(--register-tracks\)\s*;/)
    const redefinitions = [table, css].flatMap((source) =>
      topLevelRules(source).filter(([, body]) => /--register-cols\s*:/.test(body))
    )
    expect(redefinitions.map(([sel]) => sel.trim())).toEqual(['.transaction-table--running'])
  })
})
