/**
 * Money-critical tests for the shared calculator input: expressions evaluate
 * to exact cents on blur / Enter / "=", invalid expressions keep their text
 * and shake instead of silently committing, and relative mode applies leading
 * operators against the base value (assignment cells).
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { AmountInput } from './AmountInput'

function Harness({
  initial = '',
  baseCents = null as number | null,
  onKeyDown = undefined as ((e: React.KeyboardEvent<HTMLInputElement>) => void) | undefined,
}) {
  const [value, setValue] = useState(initial)
  return (
    <AmountInput
      aria-label="Amount"
      value={value}
      onValueChange={setValue}
      baseCents={baseCents}
      onKeyDown={onKeyDown}
    />
  )
}

function getInput(): HTMLInputElement {
  return screen.getByLabelText('Amount')
}

describe('AmountInput', () => {
  it('evaluates an expression on blur (receipt-sum use case)', () => {
    render(<Harness initial="12.50+3.99" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('16.49')
  })

  it('evaluates on Enter and still forwards the key to the caller', () => {
    const onKeyDown = vi.fn()
    render(<Harness initial="2*3.5" onKeyDown={onKeyDown} />)
    fireEvent.keyDown(getInput(), { key: 'Enter' })
    expect(getInput().value).toBe('7')
    expect(onKeyDown).toHaveBeenCalledTimes(1)
  })

  it('evaluates on "=" without inserting the character or forwarding the key', () => {
    const onKeyDown = vi.fn()
    render(<Harness initial="100/3" onKeyDown={onKeyDown} />)
    fireEvent.keyDown(getInput(), { key: '=' })
    expect(getInput().value).toBe('33.33')
    expect(onKeyDown).not.toHaveBeenCalled()
  })

  it('keeps the text and shakes on an invalid expression', () => {
    render(<Harness initial="12.50+" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('12.50+')
    expect(getInput().className).toContain('amount-input--shake')
  })

  it('clears the shake state when the user edits again', () => {
    render(<Harness initial="1/0" />)
    fireEvent.blur(getInput())
    expect(getInput().className).toContain('amount-input--shake')
    fireEvent.change(getInput(), { target: { value: '1/2' } })
    expect(getInput().className).not.toContain('amount-input--shake')
  })

  it('leaves plain amounts untouched on blur', () => {
    render(<Harness initial="42.10" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('42.10')
  })

  it('applies a leading operator against baseCents in relative mode', () => {
    render(<Harness initial="+50" baseCents={10000} />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('150')
  })

  it('doubles the base with "*2" in relative mode', () => {
    render(<Harness initial="*2" baseCents={10000} />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('200')
  })

  it('subtracts from the base with a bare leading minus in relative mode', () => {
    render(<Harness initial="-25" baseCents={10000} />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('75')
  })

  it('avoids float artifacts in evaluated sums (0.1+0.2)', () => {
    render(<Harness initial="0.1+0.2" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('0.30')
  })
})
