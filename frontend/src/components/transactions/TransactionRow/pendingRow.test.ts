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
  it('are derived or role tokens, never authored per theme', () => {
    // --row-hover-bg is written out in 40 theme files. The selection pair are
    // mixes against --color-accent and the pending ground is a surface role,
    // so every palette gets them and a 41st theme needs no extra lines.
    for (const token of ['--row-selected-bg', '--row-selected-hover-bg']) {
      expect(base).toMatch(new RegExp(`${token}:\\s*color-mix`))
    }
    expect(base).toMatch(/--row-pending-bg:\s*var\(--surface-sunken\)/)
  })

  it('is a surface step, not a tint of the row', () => {
    // This is the whole reason the row is legible. A tint composites a colour
    // ON TOP of the row, dragging the ground toward the text and spending the
    // text's contrast to buy colour — --color-negative already sits barely
    // above 4.5:1 on a plain row in most themes, so the ceiling was 8%, and
    // 8% of anything is a whisper. Mixing toward --text-inverse cleared AA at
    // 15%, but AA is a floor, not a target: a row falling from 13:1 to 4.6:1
    // passes the suite and is visibly harder to read. It was.
    //
    // Rows sit on --surface-raised; this is the ladder step below them.
    // Measured over all 40 variants: 26-36 units of colour away from the row
    // ground, zero AA failures, worst case 5.30:1, at most 1.5 of readability
    // given up. Adding hue on top is worse on BOTH axes in every theme.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).not.toContain('color-mix')
    expect(declaration).not.toMatch(/warning|negative|positive|accent|info/)
  })

  it('is not the sidebar ground, however close it looks', () => {
    // The sidebar carries its own --sidebar-text-* tokens, tuned for it.
    // Register text is not: painted on --sidebar-bg it fails AA in 19 of the
    // 40 variants, one at 1.00:1.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).not.toContain('sidebar')
  })
})
