import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../../../test-utils/cssRules'

/**
 * The cards strip fits a phone.
 *
 * Five columns at ~520px minimum inside `overflow-x: hidden`: on a 390pt
 * screen the fourth header read "Ready to" cut mid-word and Uncovered — the
 * figure that asks for action — was off the edge with no way to reach it.
 * The row is a two-line card on phones; this pins the shape and that every
 * numeric cell captions itself once the head row is gone.
 */
const css = stripComments(readFileSync(resolve(__dirname, 'CreditCardsSection.css'), 'utf8'))
const phone = rulesWithContext(css).filter((r) =>
  r.atRules.some((a) => a.includes('max-width: 768px'))
)
const rule = (sel: string) => phone.find((r) => r.selector.trim() === sel)?.body ?? ''

describe('credit-cards strip on a phone', () => {
  it('hides the head row', () => {
    expect(rule('.credit-cards__head')).toMatch(/display:\s*none/)
  })

  it('lays the row out as name + Uncovered over the three working figures', () => {
    const row = rule('.credit-cards__row')
    expect(row).toMatch(/grid-template-areas:\s*"name name uncovered"\s*"balance assigned ready"/)
  })

  it('captions every numeric cell, Uncovered included', () => {
    for (const [n, label] of [
      [2, 'Balance'],
      [3, 'Assigned'],
      [4, 'Ready to pay'],
      [5, 'Uncovered'],
    ] as const) {
      expect(rule(`.credit-cards__row > :nth-child(${n})::before`)).toContain(`content: "${label}"`)
    }
  })

  it('shows the two doors on the name line', () => {
    const touch = rulesWithContext(css).find(
      (r) =>
        r.atRules.some((a) => a.includes('hover: none')) &&
        r.selector.includes('.credit-cards__target-btn')
    )
    expect(touch?.body).toMatch(/opacity:\s*1/)
  })
})
