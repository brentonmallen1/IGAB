import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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
    // The five the backend seeds (repositories/tag_repo.py SYSTEM_TAGS), in order.
    expect(SYSTEM_TAG_HELP.map((t) => t.key)).toEqual([
      'subscription',
      'savings',
      'long_term_expense',
      'debt_principal',
      'essential',
    ])
  })

  it('stays closed until asked', () => {
    render(<SystemTagsHelp />)
    expect(screen.queryByText('Each one')).not.toBeInTheDocument()
  })
})
