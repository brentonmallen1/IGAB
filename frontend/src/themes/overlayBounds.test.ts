import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { stripComments, topLevelRules } from '../test-utils/cssRules'

/**
 * Nothing may render off the screen with no way to reach it.
 *
 * Overlay geometry has been consolidated twice. The first round collapsed
 * five copies of the arithmetic into `utils/anchoredPosition.ts`. By the
 * second, three more surfaces were off-screen again — and one of them,
 * `.header__theme-dropdown`, had never had any JS at all: `position:
 * absolute`, `overflow: hidden`, no cap, and nineteen palettes to list. The
 * options past the viewport edge were not merely off-screen, they were
 * unreachable. No amount of care in the shared helper reaches a panel that
 * never asked it anything.
 *
 * So this test reads the real stylesheets and holds every anchored floating
 * panel to the contract:
 *
 *   1. its height is bounded — by its own `max-height`, or by the measured
 *      cap `useAnchoredPosition` supplies inline; and
 *   2. it can scroll, so a bounded panel still reaches its last row.
 *
 * Bounded without scrolling is the same defect wearing a cap: the content is
 * clipped instead of overflowing, and just as unreachable.
 *
 * The panels are found by the z-index token they declare, which is the
 * vocabulary base.css already defines for exactly this class of thing —
 * `--z-dropdown` is documented there as "popover or menu attached to a
 * control". A new dropdown that picks one of these tokens is covered the day
 * it is written; one that invents its own z-index is not, which is the known
 * limit of this check and a reason to keep using the tokens.
 */

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

/** The z-index tokens that mean "a floating panel attached to a control". */
const PANEL_LAYERS = ['--z-dropdown', '--z-page-chrome', '--z-tooltip']

const BOUNDED = /max-height\s*:/
const SCROLLS = /overflow(-y)?\s*:\s*[^;]*\b(auto|scroll)\b/

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return cssFiles(full)
    return full.endsWith('.css') ? [full] : []
  })
}

/**
 * Whether the components beside this stylesheet hand their panel to
 * `useAnchoredPosition`. Those get a measured `max-height` and an
 * `overflowY` inline, which no stylesheet scan can see — the hook is the
 * bound, and a stricter CSS rule would only be describing it a second time.
 */
function placedByTheHook(cssPath: string): boolean {
  const dir = dirname(cssPath)
  return readdirSync(dir)
    .filter((f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'))
    .some((f) => readFileSync(join(dir, f), 'utf8').includes('useAnchoredPosition'))
}

interface Panel {
  file: string
  selector: string
  body: string
}

function anchoredPanels(): Panel[] {
  const found: Panel[] = []
  for (const file of cssFiles(SRC)) {
    for (const [selector, body] of topLevelRules(stripComments(readFileSync(file, 'utf8')))) {
      // The declaration, not a mention: base.css *defines* these tokens on
      // :root, which is not a panel.
      const declaresLayer = PANEL_LAYERS.some((token) =>
        new RegExp(`z-index\\s*:\\s*var\\(\\s*${token}\\s*\\)`).test(body)
      )
      if (declaresLayer) found.push({ file, selector: selector.trim(), body })
    }
  }
  return found
}

describe('every anchored overlay is bounded and can scroll', () => {
  const panels = anchoredPanels()

  it('finds the panels at all, so a passing suite means something', () => {
    // A refactor that renamed the tokens would otherwise turn this whole file
    // into a no-op that still reports green.
    expect(panels.length).toBeGreaterThan(5)
  })

  it.each(panels.map((p) => [`${relative(SRC, p.file)} ${p.selector}`, p] as const))(
    '%s',
    (_name, panel) => {
      const byHook = placedByTheHook(panel.file)
      const bounded = byHook || BOUNDED.test(panel.body)
      const scrolls = byHook || SCROLLS.test(panel.body)

      expect(
        bounded,
        `${panel.selector} can grow past the viewport. Give it ` +
          `max-height: var(--panel-max-h), or place it with useAnchoredPosition.`
      ).toBe(true)
      expect(
        scrolls,
        `${panel.selector} is capped but cannot scroll, so the rows past the ` +
          `cap are clipped and unreachable. Add overflow-y: auto.`
      ).toBe(true)
    }
  )
})
