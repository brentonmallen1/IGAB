import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../../test-utils/cssRules'

/**
 * System scrolls itself.
 *
 * On a phone the settings shell stops scrolling its own columns and hands
 * scrolling to its container. In the budget that is MainLayout's main; System
 * sits outside MainLayout, in a box exactly the app's height, so a long
 * section ran past it and the body clipped the rest — Server Backups could
 * not be scrolled to its buttons at all. Measured in headless Chrome at
 * 390pt; jsdom has no layout, so this pins the rule that fixed it.
 */
const css = stripComments(readFileSync(resolve(__dirname, 'SystemPage.css'), 'utf8'))
const page = rulesWithContext(css).find((r) => r.selector.trim() === '.system-page')?.body ?? ''

describe('the System page on a phone', () => {
  it('is its own scroller, one app-height tall', () => {
    expect(page).toMatch(/height:\s*var\(--app-h\)/)
    expect(page).toMatch(/overflow-y:\s*auto/)
  })
})
