/**
 * A pending row reads as its own thing.
 *
 * The report: the Pending section is collapsible, and once expanded its rows
 * were hard to separate from the register around them. They were styled
 * `opacity: 0.7; font-style: italic` — pixel-identical to `unapproved`, and
 * fading the text is what made a run of them blur together in the first
 * place. They have their own ground now.
 *
 * Read as source: the interesting part is the cascade (a two-class tint beats
 * the one-class selection rule), and jsdom resolves neither `color-mix` nor
 * specificity between separate stylesheets.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { escapeRegex } from '../../../utils/payeeRegex'

const css = readFileSync(resolve(__dirname, 'TransactionRow.css'), 'utf8')
const base = readFileSync(resolve(__dirname, '../../../themes/base.css'), 'utf8')

/** The declaration block for a selector, wherever it is indented (some of
 *  these live inside `@media (hover: hover)`). */
function rule(source: string, selector: string): string {
  const start = source.search(new RegExp(`^\\s*${escapeRegex(selector)}\\s*\\{`, 'm'))
  expect(start, `${selector} is missing`).toBeGreaterThan(-1)
  return source.slice(start, source.indexOf('}', start))
}

describe('the pending row', () => {
  it('has a ground of its own', () => {
    expect(rule(css, '.transaction-row.pending')).toContain(
      'background-color: var(--row-pending-bg)'
    )
  })

  it('is no longer dimmed, so its text keeps full contrast', () => {
    expect(rule(css, '.transaction-row.pending')).not.toContain('opacity')
  })

  it('keeps a signal that is not colour', () => {
    // 40 theme variants and colour-blind readers both need the second cue.
    expect(rule(css, '.transaction-row.pending')).toContain('font-style: italic')
  })

  it('is distinguishable from an unapproved row, which it used to duplicate', () => {
    expect(rule(css, '.transaction-row.unapproved')).not.toContain('--row-pending-bg')
  })
})

describe('selection outranks provisionality', () => {
  // `.transaction-row.pending` is two classes and `.transaction-row--selected`
  // is one, so without these the tint wins and a selected pending row stops
  // looking selected.
  it('a selected pending row still reads as selected', () => {
    expect(rule(css, '.transaction-row--selected.pending')).toContain(
      'background-color: var(--row-selected-bg)'
    )
  })

  it('hover still answers on a pending row, selected or not', () => {
    expect(rule(css, '.transaction-row.pending:hover')).toContain('var(--row-hover-bg)')
    expect(rule(css, '.transaction-row--selected.pending:hover')).toContain(
      'var(--row-selected-hover-bg)'
    )
  })

  it('states the selection colours once, as tokens', () => {
    // Three rules need them — selected, selected:hover, and the pending
    // override. Literal recipes repeated across three rules is how they
    // drift; the highlight-fade animation is a different effect and keeps
    // its own values.
    expect(rule(css, '.transaction-row--selected')).toContain('var(--row-selected-bg)')
    expect(rule(css, '.transaction-row--selected:hover')).toContain('var(--row-selected-hover-bg)')
    expect(rule(css, '.transaction-row--selected.pending')).toContain('var(--row-selected-bg)')
  })
})

describe('the row tokens', () => {
  it('lifts a pending row onto the raised surface rather than washing it', () => {
    // A wash composites --text-primary over the row and drags the ground
    // toward the text, which is what cost 14 light variants their AA on
    // --text-muted and bought a per-theme exception list in contrast.test.ts.
    // --surface-raised is a real step on each palette's grey ladder: lighter
    // than the canvas in dark themes and in light ones alike, and every
    // pairing on it is one contrast.test.ts already holds through
    // `bg-secondary`.
    expect(base).toMatch(/--row-pending-bg:\s*var\(--surface-raised\);/)
  })

  it('keeps the selection pair derived, not authored per theme', () => {
    // --row-hover-bg is written out in 40 theme files. These are mixes against
    // --color-accent instead, so every palette highlights in its own accent
    // and a new theme needs no extra lines.
    for (const token of ['--row-selected-bg', '--row-selected-hover-bg']) {
      expect(base).toMatch(new RegExp(`${token}:\\s*color-mix`))
    }
  })

  it('tints pending neutrally rather than with a status colour', () => {
    // Pending is not a warning: it is money that has not moved yet, and this
    // repo reserves status colour for state that asks something of the user.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).not.toMatch(/warning|negative|positive|accent/)
  })
})
