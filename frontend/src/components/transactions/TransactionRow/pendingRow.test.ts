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

  it('is never faded, whatever else the row is', () => {
    // It used to be `opacity: 0.7`, pixel-identical to unapproved. It is now
    // pinned to 1 rather than merely left unset, because a synced pending row
    // IS also unapproved and `.transaction-row.unapproved` drops the whole row
    // to 0.65 — which composites the text toward the ground and put the
    // register's muted text and coloured amounts below AA in 40 of 40 themes.
    // A ratio measured on a token is not a ratio a faded row renders at.
    expect(rule(css, '.transaction-row.pending')).toContain('opacity: 1')
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
    // mixes against --color-accent and the pending ground is a surface role,
    // so every palette gets them and a 41st theme needs no extra lines.
    for (const token of ['--row-selected-bg', '--row-selected-hover-bg']) {
      expect(base).toMatch(new RegExp(`${token}:\\s*color-mix`))
    }
    expect(base).toMatch(/--row-pending-bg:\s*var\(--surface-raised\)/)
  })

  it('is a step the rows are not already sitting on', () => {
    // The register paints no ground of its own — .transaction-table sets no
    // background — so a row shows the page canvas straight through. And
    // --surface-sunken and --surface-canvas are BOTH var(--bg-primary): the
    // same colour the rows already sit on. So any of those as a pending ground
    // is a no-op, and a tint mixed toward --text-inverse is very nearly one
    // too, because in most dark themes --text-inverse IS --bg-primary.
    //
    // That is not hypothetical. Measured against --surface-raised, which the
    // rows do NOT sit on, a 20% --text-inverse mix over sunken scored 40/40
    // and looked excellent; measured against the ground the rows actually sit
    // on it was flat in 27 of the 40 themes. Raised is 26-36 units away and
    // flat in none of them.
    const declaration = base.match(/^\s*--row-pending-bg:\s*(.+);$/m)?.[1] ?? ''
    expect(declaration).toBe('var(--surface-raised)')
    expect(declaration).not.toMatch(/sunken|canvas|text-inverse/)
  })

  it("keeps the register's own text and its coloured amounts", () => {
    // The ground costs no readability — the worst text on it is 5.29:1, the
    // same figure those colours get on an ordinary row — so the row needs no
    // substitute palette. An override appearing on any of these means the
    // ground moved the wrong way and something is being compensated for.
    const pending = css.slice(css.indexOf('.transaction-row.pending {'))
    const block = pending.slice(0, pending.indexOf('}'))
    expect(block).not.toContain('color: var(--sidebar')
    expect(css).not.toContain('.transaction-row.pending .txn-outflow')
  })
})
