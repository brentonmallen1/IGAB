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
import { SearchHelp } from './SearchHelp'

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

  describe('Enter finishes the search', () => {
    // The box filters as you type, so Enter had nothing to submit and did
    // nothing at all: the field kept focus and its accent ring, the panel
    // stayed open, and the only way to put the search down was to click
    // somewhere else.
    it('gives up focus', () => {
      const { input } = setup()
      ;(input as HTMLInputElement).focus()
      fireEvent.change(input, { target: { value: 'coffee' } })
      expect(input).toHaveFocus()

      fireEvent.keyDown(input, { key: 'Enter' })

      expect(input).not.toHaveFocus()
    })

    it('closes the suggestions panel', () => {
      const { input } = setup()
      ;(input as HTMLInputElement).focus()
      fireEvent.change(input, { target: { value: 'is:' } })
      expect(screen.getByText('Search syntax')).toBeInTheDocument()

      fireEvent.keyDown(input, { key: 'Enter' })

      expect(screen.queryByText('Search syntax')).not.toBeInTheDocument()
    })

    it('commits the query immediately rather than waiting out the debounce', () => {
      const { input, onChange } = setup()
      ;(input as HTMLInputElement).focus()
      fireEvent.change(input, { target: { value: 'coffee' } })
      onChange.mockClear()

      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith('coffee')
    })

    it('keeps the query — Enter is not a clear', () => {
      const { input } = setup()
      ;(input as HTMLInputElement).focus()
      fireEvent.change(input, { target: { value: 'coffee' } })

      fireEvent.keyDown(input, { key: 'Enter' })

      expect((input as HTMLInputElement).value).toBe('coffee')
    })

    it('still takes a highlighted suggestion instead of dismissing', () => {
      // Arrow-down then Enter must complete the syntax and stay in the field,
      // which is the branch above this one and must keep winning.
      const { input } = setup()
      ;(input as HTMLInputElement).focus()
      fireEvent.change(input, { target: { value: 'is:' } })
      fireEvent.keyDown(input, { key: 'ArrowDown' })

      fireEvent.keyDown(input, { key: 'Enter' })

      expect(input).toHaveFocus()
      expect((input as HTMLInputElement).value).not.toBe('is:')
    })
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
  // The ⓘ lives beside the box, not in it (it used to share an edge with the
  // clear ✕ and take its clicks) — rendered here the way the register's
  // toolbar arranges the two.
  function setupWithHelp() {
    render(
      <div>
        <TransactionSearch value="" onChange={vi.fn()} />
        <SearchHelp />
      </div>
    )
  }

  it('offers help without having to focus the field first', () => {
    setupWithHelp()
    expect(screen.getByLabelText('How to search transactions')).toBeInTheDocument()
    // Not open until asked: a panel that greets everyone is one people learn
    // to dismiss without reading.
    expect(screen.queryByText('Searching transactions')).not.toBeInTheDocument()
  })

  it('explains the concepts the token list cannot', () => {
    setupWithHelp()
    fireEvent.click(screen.getByLabelText('How to search transactions'))
    expect(screen.getByText('Searching transactions')).toBeInTheDocument()
    expect(screen.getByText(/Every filter you add/)).toBeInTheDocument()
    // The lede's job: a bare number is a partial match on the amount, the
    // same way a word is a partial match on a payee.
    expect(screen.getByText(/matches any/)).toBeInTheDocument()
    expect(screen.getByText(/to widen instead of narrow/)).toBeInTheDocument()
    expect(screen.getByText(/remove one to drop just/)).toBeInTheDocument()
  })

  it('closes on Escape and gives focus back to the button', () => {
    setupWithHelp()
    const trigger = screen.getByLabelText('How to search transactions')
    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('Searching transactions')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('opening help does not pop the syntax dropdown open', () => {
    // They are different answers to different questions, and stacking both
    // over the register hides the thing being searched.
    setupWithHelp()
    fireEvent.click(screen.getByLabelText('How to search transactions'))
    expect(screen.queryByText('Search syntax')).not.toBeInTheDocument()
  })
})
