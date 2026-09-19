/**
 * Money-critical tests for the shared calculator input: expressions evaluate
 * to exact cents on blur / Enter / "=", invalid expressions keep their text
 * and shake instead of silently committing. There is no hidden operand: the
 * box is the whole equation.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { AmountInput } from './AmountInput'

function Harness({
  initial = '',
  onKeyDown = undefined as ((e: React.KeyboardEvent<HTMLInputElement>) => void) | undefined,
}) {
  const [value, setValue] = useState(initial)
  return (
    <AmountInput aria-label="Amount" value={value} onValueChange={setValue} onKeyDown={onKeyDown} />
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

  it('evaluates a leading sign as written', () => {
    render(<Harness initial="+50" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('50')
  })

  it('shakes on an operator fragment instead of inventing an operand', () => {
    // "*2" once doubled the assignment cell's current amount. There is no
    // hidden operand now, so it is simply not an equation.
    render(<Harness initial="*2" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('*2')
    expect(getInput().className).toContain('amount-input--shake')
  })

  it('leaves a bare leading minus alone — it is a sign, not arithmetic', () => {
    render(<Harness initial="-25" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('-25')
  })

  it('reads an edited negative value as written', () => {
    // The assignment cell prefills the current amount, so this is what
    // "add 20 to a -100 envelope" looks like as the user types it.
    render(<Harness initial="-100 + 20" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('-80')
  })

  it('avoids float artifacts in evaluated sums (0.1+0.2)', () => {
    render(<Harness initial="0.1+0.2" />)
    fireEvent.blur(getInput())
    expect(getInput().value).toBe('0.30')
  })
})
