import React, { forwardRef, useState } from 'react'
import {
  centsToInputString,
  evaluateExpressionCents,
  isAmountExpression,
} from '../../../utils/amountExpression'
import './AmountInput.css'

interface Props extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> {
  value: string
  onValueChange: (next: string) => void
}

/**
 * Amount input with calculator support: arithmetic expressions evaluate on
 * blur, Enter, or "=" and the field text is replaced with the result. An
 * invalid expression keeps its text and shakes — the surrounding commit
 * logic parses through the same evaluator, so an unevaluated expression can
 * never be half-read as a number.
 */
export const AmountInput = forwardRef<HTMLInputElement, Props>(function AmountInput(
  { value, onValueChange, onKeyDown, onBlur, className, ...rest },
  ref
) {
  const [shake, setShake] = useState(false)

  function evaluateInPlace() {
    if (!isAmountExpression(value)) return
    const cents = evaluateExpressionCents(value)
    if (cents === null) {
      setShake(true)
      return
    }
    onValueChange(centsToInputString(cents))
  }

  return (
    <input
      ref={ref}
      type="text"
      inputMode="decimal"
      className={`${className ?? ''}${shake ? ' amount-input--shake' : ''}`}
      value={value}
      onChange={(e) => {
        setShake(false)
        onValueChange(e.target.value)
      }}
      onKeyDown={(e) => {
        if (e.key === '=') {
          e.preventDefault()
          evaluateInPlace()
          return
        }
        if (e.key === 'Enter') evaluateInPlace()
        onKeyDown?.(e)
      }}
      onBlur={(e) => {
        evaluateInPlace()
        onBlur?.(e)
      }}
      onAnimationEnd={() => setShake(false)}
      {...rest}
    />
  )
})
