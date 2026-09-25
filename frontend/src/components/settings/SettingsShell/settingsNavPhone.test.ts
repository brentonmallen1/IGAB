import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { rulesWithContext, stripComments } from '../../../test-utils/cssRules'

/**
 * On a phone the section list is a list of things to tap.
 *
 * It was secondary-grey text on the page ground with a hairline between
 * rows — Settings and System both — and read as a paragraph with rules in
 * it. The rows now sit on a raised, bordered card with a visible chevron,
 * the phone's own settings-list idiom. Checked in headless Chrome at 390pt
 * in light and dark; this pins the rules that draw it.
 */
const css = stripComments(readFileSync(resolve(__dirname, 'SettingsShell.css'), 'utf8'))
const phone = (selector: string) =>
  rulesWithContext(css).find(
    (r) => r.selector.trim() === selector && r.atRules.some((a) => a.includes('max-width: 768px'))
  )?.body ?? ''

describe('the settings section list on a phone', () => {
  it('draws each row on a raised, bordered card in full-strength text', () => {
    const row = phone('.settings-nav__link')
    expect(row).toMatch(/background-color:\s*var\(--surface-raised\)/)
    expect(row).toMatch(/border:\s*1px solid var\(--edge\)/)
    expect(row).toMatch(/color:\s*var\(--text-primary\)/)
    expect(row).toMatch(/min-height:\s*var\(--tap-min\)/)
  })

  it('answers a press', () => {
    expect(phone('.settings-nav__link:active')).toMatch(/background-color:/)
  })

  it('shows the chevron', () => {
    expect(phone('.settings-nav__chevron')).toMatch(/display:\s*block/)
  })
})
