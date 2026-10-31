/**
 * The budget's colour setting, read from the stylesheets.
 *
 * jsdom resolves neither custom properties nor the cascade, so what can be
 * pinned is the contract that decides the pixels: one set of figure colours
 * (base.css, "Budget figures"), every mode re-pointing all of them, and no
 * budget component colouring a sign class of its own — each such rule was a
 * copy the setting could not reach, and ten of them existed.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { stripComments, topLevelRules } from '../test-utils/cssRules'

const SRC = resolve(__dirname, '..')
const read = (path: string) => stripComments(readFileSync(join(SRC, path), 'utf8'))
const base = read('themes/base.css')

function cssUnder(dir: string): string[] {
  return readdirSync(join(SRC, dir)).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(join(SRC, path)).isDirectory()) return cssUnder(path)
    return entry.endsWith('.css') ? [path] : []
  })
}

/** Every rule, at-rule bodies included: a colour set inside a media query is
 *  still a copy. */
function allRules(css: string): Array<[string, string]> {
  return topLevelRules(css).flatMap(([sel, body]) =>
    sel.trim().startsWith('@') || body.includes('{') ? allRules(body) : [[sel, body]]
  )
}

function declared(body: string): string[] {
  return [...body.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1])
}

/** Whitespace and quote style are Prettier's to choose, not part of the rule. */
const normal = (selector: string) => selector.replace(/\s+/g, ' ').replace(/'/g, '"').trim()
const block = (selector: string) =>
  topLevelRules(base).find(([sel]) => normal(sel) === normal(selector))?.[1] ?? ''

describe('the budget figure colours', () => {
  const defaults = declared(block(':root, [data-budget-colors]'))
  const figureVars = defaults.filter((v) => v.startsWith('--figure-'))

  it('declares both roles, both signs, and their glows', () => {
    for (const role of ['flow', 'balance']) {
      for (const sign of ['positive', 'negative']) {
        expect(figureVars).toContain(`--figure-${role}-${sign}`)
        expect(figureVars).toContain(`--figure-${role}-glow-${sign}`)
      }
    }
    expect(defaults).toContain('--budget-overspent-marker')
  })

  it('quiets only the flows under "available"', () => {
    const quiet = declared(block("[data-budget-colors='available']"))
    expect(quiet.sort()).toEqual(figureVars.filter((v) => v.startsWith('--figure-flow-')).sort())
  })

  it('quiets every figure and the overspent edge under "none"', () => {
    expect(declared(block("[data-budget-colors='none']")).sort()).toEqual(
      [...figureVars, '--budget-overspent-marker'].sort()
    )
  })

  it('draws both overspent edges from the marker', () => {
    const edge = (path: string, selector: RegExp) =>
      allRules(read(path)).find(([sel]) => selector.test(sel))?.[1] ?? ''
    expect(
      edge('components/budget/CategoryRow/CategoryRow.css', /^\s*\.category-row--overspent\s*$/)
    ).toContain('var(--budget-overspent-marker)')
    expect(
      edge(
        'components/budget/CreditCardsSection/CreditCardsSection.css',
        /pill\.negative\).*__line/
      )
    ).toContain('var(--budget-overspent-marker)')
  })
})

describe('budget components', () => {
  const files = [
    ...cssUnder('components/budget'),
    'components/transactions/QuickAddSheet/AvailableChangeToast.css',
  ]

  it('colour no sign class of their own — the figure rules in base.css do', () => {
    const copies = files.flatMap((path) =>
      allRules(read(path))
        .filter(
          ([sel, body]) =>
            /\.(positive|negative|zero|negative-on-card)\b|__[\w-]+--(positive|negative)\b/.test(
              sel
            ) && /(^|[;{\s])color\s*:/.test(body)
        )
        .map(([sel]) => `${relative(SRC, join(SRC, path))}: ${sel.trim()}`)
    )
    // Status, not sign: the overspent / underfunded envelope list and the
    // filter chips' variants name a state, like the target pills, and the
    // budget's colour setting is not about them.
    const STATUS = [
      /envelope-list--negative/,
      /budget-filter-bar__btn--/,
      /budget-tools__row--/,
      /manage-filters-modal__filter-badge--/,
    ]
    expect(copies.filter((c) => !STATUS.some((s) => s.test(c)))).toEqual([])
  })
})
