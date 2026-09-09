import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../test-utils/cssRules'

/**
 * A painted dot never grows its own hit area.
 *
 * The budget row's target LED is an 8px disc that also has to be tappable, so
 * a phone rule gave it `padding: 10px; margin: -10px` under a comment reading
 * "keep LED visually small but expand hit area". It does the opposite: the
 * element paints its own background, so the padding inflates the disc. With
 * the global `box-sizing: border-box` the declared 8px width is the border
 * box and 20px of padding overrides it — a 20px circle occupying 0px of
 * layout, sitting on top of the category name beside it.
 *
 * jsdom has no layout and would agree with any of this, so the guard reads
 * the stylesheets: a rule that paints a round background must not also pad
 * itself. The hit area belongs on a pseudo-element, which paints nothing.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

const SHEETS = [
  'components/budget/CategoryRow/CategoryRow.css',
  'components/budget/CategoryGroupRow/CategoryGroupRow.css',
  'components/transactions/TransactionRow/TransactionRow.css',
  'components/layout/Sidebar/Sidebar.css',
  'pages/GuidePage/GuidePage.css',
]

/** Selectors whose rules, anywhere in a sheet, paint a circle. */
function paintedCircles(rules: ReturnType<typeof rulesWithContext>): Set<string> {
  const circles = new Set<string>()
  for (const r of rules) {
    const paints = /background(-color)?:\s*(?!none|transparent)/.test(r.body)
    if (paints && /border-radius:\s*50%/.test(r.body)) {
      for (const s of r.selector.split(',')) circles.add(s.trim())
    }
  }
  return circles
}

describe.each(SHEETS)('%s', (file) => {
  const rules = rulesWithContext(stripComments(readFileSync(join(SRC, file), 'utf8')))
  const circles = paintedCircles(rules)

  it('has no painted circle that pads itself', () => {
    const offenders: string[] = []
    for (const r of rules) {
      const selectors = r.selector.split(',').map((s) => s.trim())
      // The element itself only; a descendant rule pads something else.
      if (!selectors.some((s) => circles.has(s))) continue
      const padding = r.body.match(/(?:^|[;{\s])padding(?:-\w+)?:\s*([^;]+)/)
      if (padding && !/^0(px)?$/.test(padding[1].trim())) {
        offenders.push(`${r.atRules.join(' ')} ${r.selector.trim()} padding: ${padding[1].trim()}`)
      }
    }
    expect(offenders, 'put the hit area on an ::after, not on the painted box').toEqual([])
  })
})

describe('the budget row LED keeps its tap area off the painted disc', () => {
  const rules = rulesWithContext(
    stripComments(readFileSync(join(SRC, 'components/budget/CategoryRow/CategoryRow.css'), 'utf8'))
  )
  const phone = (atRules: string[]) => atRules.some((a) => /max-width:\s*768px/.test(a))

  it('expands it on a pseudo-element in the phone block', () => {
    const after = rules.find(
      (r) => r.selector.trim() === '.category-row__target-led::after' && phone(r.atRules)
    )
    expect(after?.body).toMatch(/position:\s*absolute/)
    expect(after?.body).toMatch(/inset:\s*-\d+px/)
  })

  it('positions the LED so that pseudo-element has something to anchor to', () => {
    const led = rules.find(
      (r) => r.selector.trim() === '.category-row__target-led' && phone(r.atRules)
    )
    expect(led?.body).toMatch(/position:\s*relative/)
  })
})
