import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AttentionDot } from './AttentionDot'

const clear = { uncategorized_count: 0, unapproved_count: 0, pending_count: 0 }

describe('AttentionDot', () => {
  it('draws nothing for a clear account', () => {
    const { container } = render(<AttentionDot counts={clear} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('is a warning dot, named for what is waiting, when rows need the person', () => {
    render(<AttentionDot counts={{ ...clear, unapproved_count: 5, pending_count: 2 }} />)
    const dot = screen.getByRole('img', { name: '5 to approve · 2 pending' })
    expect(dot).toHaveClass('count-badge--dot', 'count-badge--warning')
    // No number on the row: the count is the label, not the mark.
    expect(dot).toBeEmptyDOMElement()
  })

  it('is muted when rows are only pending', () => {
    render(<AttentionDot counts={{ ...clear, pending_count: 1 }} />)
    expect(screen.getByRole('img', { name: '1 pending' })).toHaveClass('count-badge--muted')
  })
})
