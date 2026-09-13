import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { stripComments, topLevelRules } from '../../test-utils/cssRules'

/**
 * A checkbox inside a Guide tool is not a text field.
 *
 * `.tool input` gives every input a text field's padding and a
 * `--tap-min` min-height, and `.tool__field input` / `.tool__table input`
 * stretch it to its column. A native checkbox handed that box is drawn to fill
 * it: the How money counts explorer's toggles rendered as 44px squares, and the
 * payoff planner's include column the same. Measured in headless Chrome, 13×44
 * before the reset and 13×13 after. Read as source because jsdom resolves
 * neither the cascade nor the box.
 */
const css = stripComments(readFileSync(resolve(__dirname, 'GuidePage.css'), 'utf8'))

describe('Guide tool checkboxes', () => {
  it('are reset from the text-field box', () => {
    const reset = topLevelRules(css).find(([sel]) =>
      sel.includes('.tool input:is([type="checkbox"], [type="radio"])')
    )
    expect(reset).toBeDefined()
    const body = reset![1]
    expect(body).toMatch(/min-height\s*:\s*0/)
    expect(body).toMatch(/width\s*:\s*auto/)
    expect(body).toMatch(/padding\s*:\s*0/)
  })
})
