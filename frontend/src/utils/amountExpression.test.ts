/**
 * The calculator inputs feed real money writes, so the evaluator gets the
 * exhaustive treatment: float traps, operator precedence, relative-to-base
 * semantics, separator conventions, and every rejection path.
 */
import { describe, expect, it } from 'vitest'

import {
  centsToInputString,
  evaluateExpressionCents,
  expressionToCents,
  isAmountExpression,
  parseAmountExpressionInput,
  parseAssignmentInput,
} from './amountExpression'

describe('isAmountExpression', () => {
  it('flags arithmetic and passes plain amounts through', () => {
    expect(isAmountExpression('12.50+3.99')).toBe(true)
    expect(isAmountExpression('10-2')).toBe(true)
    expect(isAmountExpression('(1+2)*3')).toBe(true)
    expect(isAmountExpression('12.50')).toBe(false)
    expect(isAmountExpression('1,234.56')).toBe(false)
    expect(isAmountExpression('')).toBe(false)
    expect(isAmountExpression('   ')).toBe(false)
  })

  it('treats a single leading minus as a sign, not arithmetic', () => {
    expect(isAmountExpression('-25')).toBe(false)
  })

  it('relative mode: any leading operator is an expression against the base', () => {
    expect(isAmountExpression('-25', true)).toBe(true)
    expect(isAmountExpression('+50', true)).toBe(true)
    expect(isAmountExpression('*2', true)).toBe(true)
    expect(isAmountExpression('/2', true)).toBe(true)
    expect(isAmountExpression('50', true)).toBe(false)
  })
})

describe('evaluateExpressionCents', () => {
  it('sums receipt items exactly (the QuickAdd killer use)', () => {
    expect(evaluateExpressionCents('12.50+3.99')).toBe(1649)
  })

  it('does not inherit binary float artifacts', () => {
    // 0.1 + 0.2 !== 0.3 in floats; in cents it is exactly 30
    expect(evaluateExpressionCents('0.1+0.2')).toBe(30)
    expect(evaluateExpressionCents('999.99-999.89')).toBe(10)
    expect(evaluateExpressionCents('1.10-1.00-0.10')).toBe(0)
  })

  it('handles precedence and parentheses', () => {
    expect(evaluateExpressionCents('2+3*4')).toBe(1400)
    expect(evaluateExpressionCents('(2+3)*4')).toBe(2000)
    expect(evaluateExpressionCents('10-2-3')).toBe(500)
  })

  it('multiplies and divides through the cents scale correctly', () => {
    expect(evaluateExpressionCents('12.50*2')).toBe(2500)
    expect(evaluateExpressionCents('100/3')).toBe(3333) // rounds once, at the end
    expect(evaluateExpressionCents('10/4')).toBe(250)
    expect(evaluateExpressionCents('0.10*0.5')).toBe(5)
  })

  it('supports unary minus inside expressions', () => {
    expect(evaluateExpressionCents('-5+10')).toBe(500)
    expect(evaluateExpressionCents('5*-2')).toBe(-1000)
  })

  it('ignores whitespace and currency symbols', () => {
    expect(evaluateExpressionCents(' 12.50 + 3.99 ')).toBe(1649)
    expect(evaluateExpressionCents('$5+$2.25')).toBe(725)
  })

  it('handles separator conventions inside literals', () => {
    expect(evaluateExpressionCents('1,234.56+0.44')).toBe(123500)
    expect(evaluateExpressionCents('12,34+1')).toBe(1334) // decimal comma
    expect(evaluateExpressionCents('1,234+1')).toBe(123500) // grouping comma
  })

  it('applies a leading operator against the base in relative mode', () => {
    expect(evaluateExpressionCents('+50', 10000)).toBe(15000)
    expect(evaluateExpressionCents('-25', 10000)).toBe(7500)
    expect(evaluateExpressionCents('*2', 10000)).toBe(20000)
    expect(evaluateExpressionCents('/2', 10000)).toBe(5000)
    // Without a leading operator the base is ignored
    expect(evaluateExpressionCents('50', 10000)).toBe(5000)
  })

  it('rounds half away from zero at the end only', () => {
    expect(evaluateExpressionCents('0.01/2')).toBe(1) // 0.5 cents up
    expect(evaluateExpressionCents('-0.01/2')).toBe(-1) // symmetric for refunds
  })

  it('rejects invalid input with null', () => {
    expect(evaluateExpressionCents('')).toBeNull()
    expect(evaluateExpressionCents('abc')).toBeNull()
    expect(evaluateExpressionCents('1+')).toBeNull()
    expect(evaluateExpressionCents('(1+2')).toBeNull()
    expect(evaluateExpressionCents('1)2')).toBeNull()
    expect(evaluateExpressionCents('1/0')).toBeNull()
    expect(evaluateExpressionCents('1.2.3')).toBeNull()
    expect(evaluateExpressionCents('..')).toBeNull()
  })
})

describe('parseAmountExpressionInput', () => {
  it('evaluates expressions to non-negative dollars', () => {
    expect(parseAmountExpressionInput('12.50+3.99')).toBe(16.49)
    expect(parseAmountExpressionInput('10*3')).toBe(30)
  })

  it('falls back to plain parsing for non-expressions', () => {
    expect(parseAmountExpressionInput('12,34')).toBe(12.34)
    expect(parseAmountExpressionInput('1,234.56')).toBe(1234.56)
  })

  it('rejects negative results — sign is structural in outflow/inflow fields', () => {
    expect(parseAmountExpressionInput('5-10')).toBeNaN()
    expect(parseAmountExpressionInput('-25')).toBeNaN()
  })

  it('rejects garbage', () => {
    expect(parseAmountExpressionInput('1+')).toBeNaN()
    expect(parseAmountExpressionInput('')).toBeNaN()
  })
})

describe('expressionToCents', () => {
  it('evaluates expressions for validation sums', () => {
    expect(expressionToCents('1.00+0.10')).toBe(110)
  })

  it('keeps plain-value behavior identical to toCents', () => {
    expect(expressionToCents('3.33')).toBe(333)
    expect(expressionToCents('')).toBeNaN()
  })

  it('invalid or negative expressions are NaN, never a partial parse', () => {
    // parseFloat('3.33+1') would silently give 3.33 — that must not happen
    expect(expressionToCents('3.33+')).toBeNaN()
    expect(expressionToCents('1-2')).toBeNaN()
  })
})

describe('parseAssignmentInput', () => {
  it('plain values set absolutely', () => {
    expect(parseAssignmentInput('550', 100)).toBe(550)
    // A negative assignment must be typed as arithmetic ("0-25") — a bare
    // leading minus always means "subtract from current" in the cell
    expect(parseAssignmentInput('0-25', 100)).toBe(-25)
  })

  it('leading operators adjust the current value', () => {
    expect(parseAssignmentInput('+50', 100)).toBe(150)
    expect(parseAssignmentInput('-25', 100)).toBe(75)
    expect(parseAssignmentInput('*2', 100)).toBe(200)
    expect(parseAssignmentInput('/2', 100)).toBe(50)
  })

  it('full expressions work too', () => {
    expect(parseAssignmentInput('100+50*2', 0)).toBe(200)
  })

  it('invalid input is NaN so the commit path can refuse to write $0', () => {
    expect(parseAssignmentInput('+', 100)).toBeNaN()
    expect(parseAssignmentInput('abc', 100)).toBeNaN()
  })
})

describe('centsToInputString', () => {
  it('renders whole dollars compactly and cents at two places', () => {
    expect(centsToInputString(55000)).toBe('550')
    expect(centsToInputString(1649)).toBe('16.49')
    expect(centsToInputString(-1234)).toBe('-12.34')
    expect(centsToInputString(0)).toBe('0')
  })
})
