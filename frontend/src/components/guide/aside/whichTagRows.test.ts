import { describe, expect, it } from 'vitest'
import { SYSTEM_TAG_HELP } from '../../settings/TagsPanel/systemTagHelp'
import { WHICH_TAG_ROWS, whichTagKeys } from './whichTagRows'

describe('which tag do I use', () => {
  it('names only tags the Tags panel explains', () => {
    const known = SYSTEM_TAG_HELP.map((t) => t.key)
    for (const key of whichTagKeys()) expect(known, key).toContain(key)
  })

  it('has the six rows, the emergency fund marked as its default mode', () => {
    expect(WHICH_TAG_ROWS).toHaveLength(6)
    const fund = WHICH_TAG_ROWS.find((r) => r.tags.includes('emergency_fund'))!
    expect(fund).toMatchObject({ mode: 'kept_here', modeIsDefault: true })
    expect(WHICH_TAG_ROWS.find((r) => r.tags.includes('long_term_expense'))?.mode).toBeNull()
  })
})
