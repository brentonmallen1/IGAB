/**
 * The calculator inputs feed real money writes, so the evaluator gets the
 * exhaustive treatment: float traps, operator precedence, separator
 * conventions, and every rejection path.
 */
import { describe, expect, it } from 'vitest'

import {
  centsToInputString,
  evaluateExpressionCents,
  expressionToCents,
  isAmountExpression,
  parseAmountExpressionInput,
  parseAssignmentCommit,
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

  it('flags an operator fragment so the evaluator can reject it', () => {
    expect(isAmountExpression('+50')).toBe(true)
    expect(isAmountExpression('*2')).toBe(true)
    expect(isAmountExpression('/2')).toBe(true)
    expect(isAmountExpression('50')).toBe(false)
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

  it('reads a leading sign as a sign and nothing else', () => {
    expect(evaluateExpressionCents('-100+20')).toBe(-8000)
    expect(evaluateExpressionCents('-100')).toBe(-10000)
    expect(evaluateExpressionCents('+50')).toBe(5000)
  })

  it('rejects an operator fragment — it is not an equation', () => {
    // "*2" once meant "double what is already assigned". Nothing outside the
    // box is an operand now, so a fragment has no meaning to guess at.
    expect(evaluateExpressionCents('*2')).toBeNull()
    expect(evaluateExpressionCents('/2')).toBeNull()
    expect(evaluateExpressionCents('+')).toBeNull()
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

describe('expressionToCents — typed text, not a canonical string', () => {
  it('reads separators the same way with or without arithmetic', () => {
    // These two disagreed by a factor of 1250: the plain value went through
    // parseFloat ("1,250" → 1) and the expression through the tokenizer.
    // Quick Add saved a one-dollar transaction for a $1,250 purchase.
    expect(expressionToCents('1,250')).toBe(125000)
    expect(expressionToCents('1,250+0')).toBe(125000)
    expect(expressionToCents('12,34')).toBe(1234) // decimal comma
    expect(expressionToCents('12,34+0')).toBe(1234)
  })

  it('refuses a negative on both paths', () => {
    // A bare "-5" used to return -500 and skip the rule the expression path
    // enforces — a negative split leg where "1-6" was rejected.
    expect(expressionToCents('-5')).toBeNaN()
    expect(expressionToCents('1-6')).toBeNaN()
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

/**
 * The commit rule the three assignment cells share. Before it was extracted
 * the grid row and the multi-month sheet spelled it inline and the cards
 * strip omitted it — clearing that box silently kept the old amount, and it
 * rejected the two other things an assignment is allowed to be.
 */
describe('parseAssignmentCommit', () => {
  it('treats an emptied box as zero — that is how you unassign', () => {
    expect(parseAssignmentCommit('')).toBe(0)
    expect(parseAssignmentCommit('   ')).toBe(0)
  })

  it('sets an absolute amount when a plain number is typed', () => {
    expect(parseAssignmentCommit('75.25')).toBe(75.25)
    expect(parseAssignmentCommit('550')).toBe(550)
  })

  it('allows a negative assignment — money can come back off a card', () => {
    expect(parseAssignmentCommit('-25')).toBe(-25)
    expect(parseAssignmentCommit('0-25')).toBe(-25)
  })

  it('evaluates the box as a whole equation, with no hidden operand', () => {
    // Education fund, September: assigned -100 after $100 moved out of it.
    // The cell prefills "-100"; adding the month's 20 to it is the edit
    // below, and it must land on -80. It used to commit -180, because the
    // leading minus made the evaluator fold the current -100 in a second
    // time. Leaving the prefill untouched used to commit -200 for the same
    // reason.
    expect(parseAssignmentCommit('-100 + 20')).toBe(-80)
    expect(parseAssignmentCommit('-100')).toBe(-100)
    expect(parseAssignmentCommit('100-25')).toBe(75)
    expect(parseAssignmentCommit('(20+30)*2')).toBe(100)
  })

  it('is NaN for text that is not an equation, so the caller writes nothing', () => {
    expect(parseAssignmentCommit('abc')).toBeNaN()
    expect(parseAssignmentCommit('+')).toBeNaN()
    // A relative fragment. It once doubled the current assignment.
    expect(parseAssignmentCommit('*2')).toBeNaN()
  })
})
