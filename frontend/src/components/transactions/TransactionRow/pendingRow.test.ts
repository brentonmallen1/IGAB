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
  it('are derived, not authored per theme', () => {
    // --row-hover-bg is written out in 40 theme files. These are mixes against
    // --text-primary / --color-accent instead, so every palette gets them and
    // a new theme needs no extra lines.
    for (const token of ['--row-pending-bg', '--row-selected-bg', '--row-selected-hover-bg']) {
      expect(base).toMatch(new RegExp(`${token}:\\s*color-mix`))
    }
  })

  it('tints pending with a hue, but never an alarming or a claimed one', () => {
    // This used to require --text-primary, i.e. a neutral grey wash. That is
    // the same grey the hover and the zebra are made of, so a pending row read
    // as "slightly dimmer" rather than as a state and was findable only by its
    // italics. It is --color-info now.
    //
    // What did NOT change is what stays forbidden, and the reasons are
    // different for each: warning/negative would say a pending row is a
    // problem, and it is not — it is money that has not moved yet. --accent is
    // barred for a harder reason: --row-selected-bg is mixed from it, so an
    // accent-washed pending row would be mistakable for a selected one.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).toContain('--color-info')
    expect(declaration).not.toMatch(/warning|negative|positive|accent/)
  })

  it('mixes away from the text, not on top of it', () => {
    // This is the whole reason the row is visible at all. A translucent wash
    // composites a mid-tone colour ON TOP of the row, dragging the ground
    // toward the text and spending the text's contrast to buy colour — and
    // --color-negative already sits barely above 4.5:1 on a plain row in most
    // themes, so the ceiling was 8%. Every hue capped the same way (info 8%,
    // warning 7%, tag-teal 6%): the limit was the direction, not the hue.
    //
    // Mixing toward --text-inverse moves the ground AWAY from the text, so
    // contrast RISES as the colour strengthens. 18% before any theme
    // complains, and roughly double the visible difference.
    //
    // The second operand must stay --text-inverse. Swap it for `transparent`
    // and this is a wash again, at a strength no theme can carry.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).toMatch(/var\(--color-info\) 15%/)
    expect(declaration).toContain('var(--text-inverse)')
    expect(declaration).not.toContain('transparent')
  })
})
