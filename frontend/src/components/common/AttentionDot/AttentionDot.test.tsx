import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AttentionDot } from './AttentionDot'

const clear = { uncategorized_count: 0, unapproved_count: 0, pending_count: 0 }

describe('AttentionDot', () => {
  it('draws nothing for a clear account', () => {
    const { container } = render(<AttentionDot counts={clear} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('is a warning dot, named for what is waiting, when rows wait to be filed', () => {
    render(<AttentionDot counts={{ ...clear, uncategorized_count: 1, unapproved_count: 5 }} />)
    const dot = screen.getByRole('img', { name: '1 to categorize · 5 to approve' })
    expect(dot).toHaveClass('count-badge--dot', 'count-badge--warning')
    // No number on the row: the count is the label, not the mark.
    expect(dot).toBeEmptyDOMElement()
  })

  it('is an info dot when rows wait only to be approved', () => {
    render(<AttentionDot counts={{ ...clear, unapproved_count: 5, pending_count: 2 }} />)
    const dot = screen.getByRole('img', { name: '5 to approve · 2 pending' })
    expect(dot).toHaveClass('count-badge--dot', 'count-badge--info')
    expect(dot).not.toHaveClass('count-badge--warning')
    expect(dot).toBeEmptyDOMElement()
  })

  it('is muted when rows are only pending', () => {
    render(<AttentionDot counts={{ ...clear, pending_count: 1 }} />)
    expect(screen.getByRole('img', { name: '1 pending' })).toHaveClass('count-badge--muted')
  })
})
