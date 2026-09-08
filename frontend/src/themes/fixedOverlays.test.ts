import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { stripComments, topLevelRules } from '../test-utils/cssRules'

/**
 * Every modal overlay is built on Modal, BottomSheet or Dialog.
 *
 * Nine components had hand-rolled their own — a fixed full-screen div with
 * a focus trap and nothing else: no history entry (Android back left the
 * page), no place on the overlay stack (Escape closed two things), no scroll
 * lock, and on a phone no drag, no 44px close, sometimes no close at all.
 * Each was plausible when written. This test reads every stylesheet and
 * fails on a top-level `position: fixed` rule at an overlay z-token outside
 * the files that own the primitives.
 *
 * Anchored popovers (--z-dropdown) and non-modal bars (--z-float, --z-nav)
 * use other tokens and are not the subject; the contract for them lives in
 * overlayBounds.test.ts.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '..')

const OVERLAY_TOKENS = ['--z-overlay', '--z-overlay-backdrop', '--z-nested-overlay']

/** The primitives, plus the surfaces that are the primitive for their kind. */
const OWNERS: Record<string, string> = {
  'components/common/Modal/Modal.css': 'the modal primitive',
  'components/common/BottomSheet/BottomSheet.css': 'the sheet primitive',
  'components/common/SideDrawer/SideDrawer.css':
    'the docked-drawer primitive (no backdrop by design)',
  'components/attachments/Lightbox.css':
    'the image viewer: on the overlay stack with a history entry and a __close button',
  'components/palette/CommandPalette/CommandPalette.css':
    'the command palette: its own top sheet with close, backdrop and history; a drag would fight its list',
}

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return cssFiles(full)
    return full.endsWith('.css') ? [full] : []
  })
}

function fixedOverlayRules(): Array<{ file: string; selector: string }> {
  const found: Array<{ file: string; selector: string }> = []
  for (const file of cssFiles(SRC)) {
    const rel = relative(SRC, file)
    for (const [selector, body] of topLevelRules(stripComments(readFileSync(file, 'utf8')))) {
      const fixed = /position\s*:\s*fixed/.test(body)
      const overlayLayer = OVERLAY_TOKENS.some((t) =>
        new RegExp(`z-index\\s*:\\s*var\\(\\s*${t}\\s*\\)`).test(body)
      )
      if (fixed && overlayLayer) found.push({ file: rel, selector: selector.trim() })
    }
  }
  return found
}

describe('modal overlays are built on the primitives', () => {
  const found = fixedOverlayRules()

  it('finds the primitives themselves (a green run must mean something)', () => {
    const files = new Set(found.map((f) => f.file))
    expect(files.has('components/common/Modal/Modal.css')).toBe(true)
    expect(files.has('components/common/BottomSheet/BottomSheet.css')).toBe(true)
  })

  it('finds no hand-rolled overlay', () => {
    const strays = found.filter((f) => !(f.file in OWNERS))
    const message = strays
      .map(
        (f) =>
          `${f.file}: ${f.selector} is a fixed overlay outside the primitives. Render through ` +
          `Dialog (or Modal / BottomSheet) instead — it supplies the close button, history entry, ` +
          `overlay stack and scroll lock.`
      )
      .join('\n')
    expect(strays, message).toEqual([])
  })

  it('keeps every owner honest — an owner with no fixed overlay rule is a stale entry', () => {
    const files = new Set(found.map((f) => f.file))
    for (const owner of Object.keys(OWNERS)) {
      expect(files.has(owner), `${owner}: ${OWNERS[owner]}`).toBe(true)
    }
  })
})
