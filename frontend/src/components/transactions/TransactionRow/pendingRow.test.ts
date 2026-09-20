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

  it('does not claim the row marker', () => {
    // It did, briefly, to carry a hue the old translucent ground could not.
    // Expanded, that drew an edge beside every row in the section, under a
    // header that already had one — a box round the section rather than a
    // mark on a row. The ground carries pending; the marker means one thing.
    expect(rule(css, '.transaction-row.pending')).not.toContain('--row-marker')
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
  it('need no per-theme authoring of their own', () => {
    // --row-hover-bg is written out in 40 theme files. The selection pair are
    // mixes against --color-accent, and the pending ground forwards a token
    // every palette already authors for its sidebar — so a 41st theme gets
    // all three by writing the values it was going to write anyway.
    for (const token of ['--row-selected-bg', '--row-selected-hover-bg']) {
      expect(base).toMatch(new RegExp(`${token}:\\s*color-mix`))
    }
    expect(base).toMatch(/--row-pending-bg:\s*var\(--sidebar-bg\)/)
  })

  it('is the sidebar ground, and brings the sidebar text with it', () => {
    // A design call: an entirely different surface rather than a tint of the
    // row. Both tints failed, and failed differently. A translucent wash
    // composites a colour ON TOP of the row, dragging the ground toward the
    // text and spending the text's contrast to buy colour — the ceiling was
    // 8%, and 8% of anything is a whisper. Mixing toward --text-inverse
    // cleared AA at 15%, but AA is a floor, not a target: a row falling from
    // 13:1 to 4.6:1 passes the suite and is visibly harder to read.
    //
    // A ground this far from the register's own has to bring its text with
    // it. The sidebar tokens are authored per palette against exactly this
    // background and contrast.test.ts holds all three to AA on it in every
    // theme; the register's own --text-* are not, and land as low as 1.06:1.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).toBe('var(--sidebar-bg)')
    expect(rule(css, '.transaction-row.pending')).toContain('color: var(--sidebar-text-primary)')
  })

  it('prints its amount in sidebar text, not the register red and green', () => {
    // --color-negative/--color-positive fail AA on this ground in 19 of the 40
    // themes — every light one, whose sidebar stays dark while its semantic
    // colours are tuned for a light ground. nord-light lands at 1.69:1. The
    // row still states its sign the way the register always does: a leading
    // minus, and the Outflow/Inflow column it sits in.
    const amounts = css.slice(css.indexOf('.transaction-row.pending .txn-outflow'))
    expect(amounts.slice(0, amounts.indexOf('}'))).toContain('var(--sidebar-text-primary)')
  })

  it('is fully opaque — a different surface, not a quieter one', () => {
    expect(rule(css, '.transaction-row.pending')).not.toContain('opacity')
  })
})
