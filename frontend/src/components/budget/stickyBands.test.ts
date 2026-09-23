import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../../test-utils/cssRules'

/**
 * The budget grid stacks bands that pin as you scroll: the filter bar at the
 * top, the credit-cards header under it, the column header under that. jsdom
 * has no layout, so what a test can hold is that each names the same measured
 * offset rather than a guessed constant — two stacked stickies that disagree
 * show a sliver of scrolling rows between them at one window width and clip
 * one another at the next.
 *
 * `--budget-filter-bar-h` is published by BudgetTable from the live height of
 * the filter bar (it wraps, so no number in a stylesheet is right).
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', '..')

function declarations(file: string, selector: string): Record<string, string> {
  const rules = rulesWithContext(stripComments(readFileSync(join(SRC, file), 'utf8')))
  const hit = rules.find((r) => r.selector.split(',').some((s) => s.trim() === selector))
  if (!hit) throw new Error(`${file} has no rule for ${selector}`)
  return Object.fromEntries(
    hit.body
      .split(';')
      .map((d) => d.split(/:(.*)/s))
      .filter((pair) => pair.length > 1)
      .map(([k, v]) => [k.trim(), v.trim()])
  )
}

describe('the budget grid’s stacked sticky bands', () => {
  it('the filter bar pins at the very top', () => {
    const d = declarations(
      'components/budget/BudgetFilterBar/BudgetFilterBar.css',
      '.budget-filter-bar'
    )
    expect(d['position']).toBe('sticky')
    expect(d['top']).toBe('0')
  })

  it('the column header sits below the filter bar’s measured height', () => {
    const d = declarations('components/budget/BudgetTable/BudgetTable.css', '.budget-table__header')
    expect(d['position']).toBe('sticky')
    expect(d['top']).toBe('var(--budget-filter-bar-h, 0px)')
  })

  it('the credit-cards band is offset by the same measurement, not a constant', () => {
    const d = declarations(
      'components/budget/CreditCardsSection/CreditCardsSection.css',
      '.credit-cards__header-row'
    )
    // It does not declare `position` itself: pinning is Surface's
    // `stickyHeader`, so "what a pinned header looks like" stays in one place
    // and this only says how far down.
    expect(d['--surface-sticky-top']).toBe('var(--budget-filter-bar-h, 0px)')
  })

  it('a pinned section header confines itself to its own section', () => {
    const d = declarations('themes/base.css', '.surface__header--sticky')
    expect(d['position']).toBe('sticky')
    // Offset is the caller's to set; 0 when nothing is pinned above.
    expect(d['top']).toBe('var(--surface-sticky-top, 0px)')
    // Opaque, or the rows sliding underneath show through it. `inherit` takes
    // whatever the variant painted, so this holds for every surface variant.
    expect(d['background-color']).toBe('inherit')
  })
})
