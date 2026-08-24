/**
 * The suggestions panel is a focus affordance — it belongs to clicking into
 * the field, never to leaving it. The regression: the clear (X) button
 * refocused the input after clearing, which popped the full syntax panel
 * open (and re-raised the mobile keyboard) at the exact moment the user was
 * done searching.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TransactionSearch } from './TransactionSearch'

function setup(value = '') {
  const onChange = vi.fn()
  render(<TransactionSearch value={value} onChange={onChange} />)
  const input = screen.getByPlaceholderText('Search transactions…')
  return { input, onChange }
}

describe('TransactionSearch suggestions', () => {
  it('focusing the empty field shows the syntax panel', () => {
    const { input } = setup()
    fireEvent.focus(input)
    expect(screen.getByText('Search syntax')).toBeInTheDocument()
  })

  it('clearing with the X closes the panel instead of re-opening it', () => {
    const { input, onChange } = setup()
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'is:' } })

    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))

    expect((input as HTMLInputElement).value).toBe('')
    expect(onChange).toHaveBeenCalledWith('')
    expect(screen.queryByText('Search syntax')).not.toBeInTheDocument()
  })

  it('typing again after a clear brings the panel back', () => {
    const { input } = setup()
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'is:' } })
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))

    fireEvent.change(input, { target: { value: 'is' } })
    expect(screen.getByText('Search syntax')).toBeInTheDocument()
  })
})

/**
 * The syntax dropdown teaches tokens to someone already looking for them.
 * This teaches that a query language exists at all — the gap that made the
 * whole feature invisible unless you happened to click into the box.
 */
describe('search help', () => {
  it('offers help without having to focus the field first', () => {
    setup()
    expect(screen.getByLabelText('How to search transactions')).toBeInTheDocument()
    // Not open until asked: a panel that greets everyone is one people learn
    // to dismiss without reading.
    expect(screen.queryByText('Searching transactions')).not.toBeInTheDocument()
  })

  it('explains the concepts the token list cannot', () => {
    setup()
    fireEvent.click(screen.getByLabelText('How to search transactions'))
    expect(screen.getByText('Searching transactions')).toBeInTheDocument()
    expect(screen.getByText(/narrows/)).toBeInTheDocument()
    expect(screen.getByText(/to widen instead of narrow/)).toBeInTheDocument()
    expect(screen.getByText(/remove one to drop just/)).toBeInTheDocument()
  })

  it('closes on Escape and gives focus back to the button', () => {
    setup()
    const trigger = screen.getByLabelText('How to search transactions')
    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('Searching transactions')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('opening help does not pop the syntax dropdown open', () => {
    // They are different answers to different questions, and stacking both
    // over the register hides the thing being searched.
    setup()
    fireEvent.click(screen.getByLabelText('How to search transactions'))
    expect(screen.queryByText('Search syntax')).not.toBeInTheDocument()
  })
})
