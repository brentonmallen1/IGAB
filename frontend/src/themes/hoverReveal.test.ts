import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { hoverRevealReport } from '../test-utils/hoverReveal'

/**
 * A control revealed only by :hover does not exist on a phone.
 *
 * The audit of 2026-09-08 found the same one-line bug four times over: an
 * action hidden with `opacity: 0` and shown by `:hover`, with no rule for a
 * screen that has no pointer. On the Activity page that was the page's ONLY
 * action (revert), on the accounts overview it was every row's edit/delete,
 * on the credit-cards strip it was the paydown-target and payoff doors. The
 * fix pattern already existed four other times (CategoryRow, TbaHero,
 * TransactionRow, CategoryGroupRow) — a `@media (hover: none)` rule that
 * shows the control — so this test reads every stylesheet and holds each
 * hover-revealed control to it.
 *
 * The heuristic, precisely:
 *   hidden control  a top-level rule with no pseudo-class in its selector
 *                   whose body sets `opacity: 0`, `visibility: hidden` or
 *                   `display: none`; keyed by the selector's last compound
 *                   (the element the rule styles).
 *   hover reveal    any rule, in any context, whose selector contains
 *                   `:hover`, styles the same key, and sets a visible value.
 *   touch restore   a same-key rule setting a visible value under
 *                   `(hover: none)` or `(max-width: 768px)`; or the hover
 *                   reveal itself sitting under `(hover: hover)` with the
 *                   hidden rule under it too (then the control is simply
 *                   never hidden on touch).
 * A control that is hidden AND hover-revealed AND not restored fails, by
 * name, with the fix in the message.
 */

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return cssFiles(full)
    return full.endsWith('.css') ? [full] : []
  })
}

/**
 * Things that are hidden and hover-revealed on purpose, and that a phone
 * reaches some other way. Each needs a reason; an entry with none is a bug
 * hiding behind a list.
 */
const EXEMPT: Record<string, string> = {
  // (none — every control found by the 2026-09-08 audit has a touch rule now)
}

const reports = cssFiles(SRC).map((file) => ({
  file: relative(SRC, file),
  ...hoverRevealReport(readFileSync(file, 'utf8')),
}))

describe('every hover-revealed control has a touch rule', () => {
  it('finds the hover-reveal pattern at all (a green run must mean something)', () => {
    const total = reports.reduce((n, r) => n + r.hoverRevealed.length, 0)
    expect(total).toBeGreaterThanOrEqual(6)
  })

  it('reports none without a reason', () => {
    const found = reports.flatMap((r) =>
      r.unrestored
        .filter((key) => !(`${r.file} ${key}` in EXEMPT))
        .map((key) => `${r.file}: ${key} is revealed only by :hover`)
    )
    const message =
      found.join('\n') +
      '\nAdd a @media (hover: none) rule that shows it (see CategoryRow.css), or move both ' +
      'rules under @media (hover: hover).'
    expect(found, message).toEqual([])
  })

  it('keeps every exemption honest — an entry for a control that is no longer hover-only is stale', () => {
    for (const entry of Object.keys(EXEMPT)) {
      const [file, key] = entry.split(' ')
      const r = reports.find((x) => x.file === file)
      expect(r?.unrestored, entry).toContain(key)
    }
  })
})
