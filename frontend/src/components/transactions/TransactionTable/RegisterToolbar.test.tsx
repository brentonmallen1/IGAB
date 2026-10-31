/**
 * The pay button used to live at the end of the liability terms strip, styled
 * like "Edit terms" — an action dressed as metadata. These pin its new home:
 * in the toolbar beside Add Transaction, and only on registers that take a
 * payment at all.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RegisterToolbar } from './RegisterToolbar'
import { registerToggles } from './registerToggles'

function toggleState(over: { showSplitLines?: boolean; showRunningBalance?: boolean } = {}) {
  return {
    showSplitLines: false,
    setShowSplitLines: vi.fn(),
    showRunningBalance: false,
    setShowRunningBalance: vi.fn(),
    ...over,
  }
}

const base = {
  searchQuery: '',
  onSearchChange: vi.fn(),
  onAdd: vi.fn(),
  toggles: registerToggles(toggleState(), false),
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

  it.each([
    ['split lines', 'showSplitLines', 'setShowSplitLines'],
    ['running balance', 'showRunningBalance', 'setShowRunningBalance'],
  ] as const)(
    'toggles %s: a pressed state, a name that stays put, a tooltip saying what a click does',
    (noun, key, setter) => {
      const off = toggleState()
      const { rerender } = render(
        <RegisterToolbar {...base} pay={null} toggles={registerToggles(off, false)} />
      )
      const toggle = screen.getByRole('button', { name: `Show ${noun}` })
      expect(toggle).toHaveAttribute('aria-pressed', 'false')
      expect(toggle).toHaveAttribute('title', `Show ${noun}`)
      fireEvent.click(toggle)
      expect(off[setter]).toHaveBeenLastCalledWith(true)

      const on = toggleState({ [key]: true })
      rerender(<RegisterToolbar {...base} pay={null} toggles={registerToggles(on, false)} />)
      const pressed = screen.getByRole('button', { name: `Show ${noun}` })
      expect(pressed).toHaveAttribute('aria-pressed', 'true')
      expect(pressed).toHaveAttribute('title', `Hide ${noun}`)
      fireEvent.click(pressed)
      expect(on[setter]).toHaveBeenLastCalledWith(false)
    }
  )

  it('offers no running balance on the all-accounts register', () => {
    // Across accounts a running total is not a balance of anything.
    render(<RegisterToolbar {...base} pay={null} toggles={registerToggles(toggleState(), true)} />)
    expect(screen.getByRole('button', { name: 'Show split lines' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show running balance' })).toBeNull()
  })

  // On the phone account page the toggles live in Tools, leaving this row to
  // the search box.
  it('draws no toggles where the page puts them elsewhere', () => {
    render(<RegisterToolbar {...base} pay={null} toggles={[]} />)
    expect(screen.queryByRole('button', { name: 'Show split lines' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Show running balance' })).toBeNull()
  })
})
