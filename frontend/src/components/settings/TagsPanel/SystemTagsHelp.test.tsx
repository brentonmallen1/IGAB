import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import systemTags from '../../../../../shared/system_tags.json'
import { SystemTagsHelp } from './SystemTagsHelp'
import { SYSTEM_TAG_HELP } from './systemTagHelp'

describe('SystemTagsHelp', () => {
  it('names every system tag and what it changes', () => {
    render(<SystemTagsHelp />)
    fireEvent.click(screen.getByLabelText('What system tags do'))
    for (const tag of SYSTEM_TAG_HELP) {
      expect(screen.getByText(tag.name)).toBeInTheDocument()
      expect(tag.does.length).toBeGreaterThan(40)
    }
    // Every tag the backend seeds, in its order. The list is shared with
    // backend/tests/unit/test_system_tags_agree.py: a hand-copied one here let
    // `cost_of_living` ship with no explanation while this test stayed green.
    expect(SYSTEM_TAG_HELP.map((t) => t.key)).toEqual(systemTags.keys)
  })

  it('stays closed until asked', () => {
    render(<SystemTagsHelp />)
    expect(screen.queryByText('Each one')).not.toBeInTheDocument()
  })
})
