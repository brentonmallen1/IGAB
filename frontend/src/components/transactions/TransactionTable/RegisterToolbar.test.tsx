/**
 * The pay button used to live at the end of the liability terms strip, styled
 * like "Edit terms" — an action dressed as metadata. These pin its new home:
 * in the toolbar beside Add Transaction, and only on registers that take a
 * payment at all.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RegisterToolbar } from './RegisterToolbar'

const base = {
  searchQuery: '',
  onSearchChange: vi.fn(),
  onAdd: vi.fn(),
  showSplitLines: false,
  onShowSplitLinesChange: vi.fn(),
}

describe('RegisterToolbar', () => {
  it('puts the payment beside Add Transaction and wires the click', () => {
    const onClick = vi.fn()
    render(<RegisterToolbar {...base} pay={{ label: 'Make a payment', onClick }} />)

    const pay = screen.getByRole('button', { name: 'Make a payment' })
    const add = screen.getByRole('button', { name: 'Add Transaction' })
    // Beside each other, payment first — order is part of the layout contract.
    expect(pay.compareDocumentPosition(add) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Make a payment' }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('carries the register-specific label — a loan records, a card makes', () => {
    render(<RegisterToolbar {...base} pay={{ label: 'Record a payment', onClick: vi.fn() }} />)
    expect(screen.getByRole('button', { name: 'Record a payment' })).toBeInTheDocument()
  })

  it('offers no payment on registers that take none', () => {
    const onAdd = vi.fn()
    render(<RegisterToolbar {...base} onAdd={onAdd} pay={null} />)

    expect(screen.queryByRole('button', { name: /payment/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add Transaction' }))
    expect(onAdd).toHaveBeenCalledOnce()
  })

  it('toggles split lines: a pressed state, a name that stays put, a tooltip saying what a click does', () => {
    const onShowSplitLinesChange = vi.fn()
    const { rerender } = render(
      <RegisterToolbar {...base} pay={null} onShowSplitLinesChange={onShowSplitLinesChange} />
    )
    const toggle = screen.getByRole('button', { name: 'Show split lines' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(toggle).toHaveAttribute('title', 'Show split lines')
    fireEvent.click(toggle)
    expect(onShowSplitLinesChange).toHaveBeenLastCalledWith(true)

    rerender(
      <RegisterToolbar
        {...base}
        pay={null}
        showSplitLines
        onShowSplitLinesChange={onShowSplitLinesChange}
      />
    )
    const pressed = screen.getByRole('button', { name: 'Show split lines' })
    expect(pressed).toHaveAttribute('aria-pressed', 'true')
    expect(pressed).toHaveAttribute('title', 'Hide split lines')
    fireEvent.click(pressed)
    expect(onShowSplitLinesChange).toHaveBeenLastCalledWith(false)
  })
})
