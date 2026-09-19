/**
 * Arithmetic expression evaluation for amount inputs ("12.50+3.99", "(1+2)*3").
 *
 * All literals are parsed into integer cents before any arithmetic so binary
 * float artifacts never enter sums (0.1+0.2 is exactly 30 cents here).
 * Multiplication and division may produce fractional cents mid-expression;
 * the result is rounded to a whole cent once, at the end.
 *
 * There is no hidden operand anywhere in here: an input is an equation on
 * its own terms, and what it evaluates to is the value. See
 * `parseAssignmentCommit` for the incident that settled that.
 */
import { normalizeSeparators, parseAmountInput, parseMoney, toCents } from './money'

type Token =
  | { t: 'num'; v: number } // integer cents
  | { t: 'op'; v: '+' | '-' | '*' | '/' }
  | { t: 'paren'; v: '(' | ')' }

const HAS_OPERATOR = /[+*/()]/

/**
 * Whether the text should be treated as an expression rather than a plain
 * amount. A single leading minus is a sign, not arithmetic.
 */
export function isAmountExpression(raw: string): boolean {
  const s = raw.trim()
  if (s === '') return false
  if (HAS_OPERATOR.test(s)) return true
  if (s.slice(1).includes('-')) return true
  return false
}

/** Parse one numeric literal into integer cents, or null if malformed. */
function literalToCents(tokenText: string): number | null {
  // Separator conventions live in money.ts; this parser is stricter about
  // what else it will accept, but it must read a comma the same way.
  const normalized = normalizeSeparators(tokenText)
  if (!/^(\d+(\.\d*)?|\.\d+)$/.test(normalized)) return null
  const [intPart = '0', decPart = ''] = normalized.split('.')
  // Integer dollars exactly; sub-cent digits round half-up once
  return parseInt(intPart || '0', 10) * 100 + Math.round(parseFloat(`0.${decPart || '0'}`) * 100)
}

function tokenize(raw: string): Token[] | null {
  // Currency symbols and whitespace are noise; everything else must be a
  // number, an operator, or a paren.
  const s = raw.replace(/[\s$€£¥₹₩]/g, '')
  const tokens: Token[] = []
  let i = 0
  while (i < s.length) {
    const ch = s[i]
    if (ch === '+' || ch === '-' || ch === '*' || ch === '/') {
      tokens.push({ t: 'op', v: ch })
      i++
    } else if (ch === '(' || ch === ')') {
      tokens.push({ t: 'paren', v: ch })
      i++
    } else if (/[\d.,]/.test(ch)) {
      let j = i
      while (j < s.length && /[\d.,]/.test(s[j])) j++
      const cents = literalToCents(s.slice(i, j))
      if (cents === null) return null
      tokens.push({ t: 'num', v: cents })
      i = j
    } else {
      return null
    }
  }
  return tokens
}

/** Recursive-descent evaluation over cents-scaled values. Throws on error. */
function evaluate(tokens: Token[]): number {
  let pos = 0

  function peek(): Token | undefined {
    return tokens[pos]
  }

  function expr(): number {
    let value = term()
    for (let tok = peek(); tok?.t === 'op' && (tok.v === '+' || tok.v === '-'); tok = peek()) {
      pos++
      const rhs = term()
      value = tok.v === '+' ? value + rhs : value - rhs
    }
    return value
  }

  function term(): number {
    let value = unary()
    for (let tok = peek(); tok?.t === 'op' && (tok.v === '*' || tok.v === '/'); tok = peek()) {
      pos++
      const rhs = unary()
      if (tok.v === '*') {
        // Both sides are cents-scaled (×100); rescale the product once
        value = (value * rhs) / 100
      } else {
        if (rhs === 0) throw new Error('division by zero')
        value = (value / rhs) * 100
      }
    }
    return value
  }

  function unary(): number {
    const tok = peek()
    if (tok?.t === 'op' && (tok.v === '-' || tok.v === '+')) {
      pos++
      const v = unary()
      return tok.v === '-' ? -v : v
    }
    return primary()
  }

  function primary(): number {
    const tok = peek()
    if (tok?.t === 'num') {
      pos++
      return tok.v
    }
    if (tok?.t === 'paren' && tok.v === '(') {
      pos++
      const v = expr()
      const close = peek()
      if (close?.t !== 'paren' || close.v !== ')') throw new Error('unbalanced parens')
      pos++
      return v
    }
    throw new Error('expected a number')
  }

  const result = expr()
  if (pos !== tokens.length) throw new Error('trailing input')
  return result
}

/** Evaluate an amount expression to integer cents, or null if invalid. */
export function evaluateExpressionCents(raw: string): number | null {
  const s = raw.trim()
  if (s === '') return null
  const tokens = tokenize(s)
  if (tokens === null || tokens.length === 0) return null
  let result: number
  try {
    result = evaluate(tokens)
  } catch {
    return null
  }
  if (!Number.isFinite(result) || Math.abs(result) > 1e13) return null
  // Round half away from zero — symmetric for refund math
  return Math.sign(result) * Math.round(Math.abs(result))
}

/** Render evaluated cents back into an input field ("16.49", "550"). */
export function centsToInputString(cents: number): string {
  return cents % 100 === 0 ? String(cents / 100) : (cents / 100).toFixed(2)
}

/**
 * Expression-aware replacement for parseAmountInput: evaluates arithmetic,
 * falls back to plain parsing. Returns non-negative dollars, NaN if invalid
 * or negative — outflow/inflow fields carry sign structurally.
 */
export function parseAmountExpressionInput(value: string): number {
  if (isAmountExpression(value)) {
    const cents = evaluateExpressionCents(value)
    if (cents === null || cents < 0) return NaN
    return cents / 100
  }
  return parseAmountInput(value)
}

/**
 * Expression-aware cents for typed amount fields — the Quick Add amount, the
 * split legs, and the remainder check that validates them. NaN if the input
 * is invalid or negative.
 *
 * The plain fallback is `parseAmountInput` because this reads text a person
 * typed. It used to be `toCents`, which is `parseFloat` underneath: "1,250"
 * came back as $1.00 and Quick Add saved a one-dollar transaction for it,
 * while "1,250+0" took the expression path and came back as $1,250. A bare
 * "-5" skipped the non-negative rule the expression path enforces, too.
 */
export function expressionToCents(value: string): number {
  if (isAmountExpression(value)) {
    const cents = evaluateExpressionCents(value)
    return cents === null || cents < 0 ? NaN : cents
  }
  const n = parseAmountInput(value)
  return isNaN(n) ? NaN : toCents(n)
}

/** Sum form inputs exactly in cents, expression-aware (NaN entries count 0). */
export function sumExpressionsToCents(values: string[]): number {
  return values.reduce((sum, v) => {
    const c = expressionToCents(v)
    return sum + (isNaN(c) ? 0 : c)
  }, 0)
}

/**
 * What an assignment cell commits when the user presses Enter or tabs away.
 *
 * What you see is what you get: the box holds an equation, the equation's
 * result is the amount. Nothing outside the box is an operand — the cell
 * prefills with the current amount, so the current amount is already in
 * front of you and folding it in again would charge it twice.
 *
 * That is not hypothetical. A leading operator used to apply against the
 * current assignment: "+50" added 50, "*2" doubled. Because the prefill of a
 * negative cell starts with a minus, editing a -100 envelope into
 * "-100 + 20" — the obvious way to add the month's 20 to it — evaluated as
 * (-100) + (-100) + 20 and committed -180. Opening the same cell and tabbing
 * away without touching it committed -200. Retyping could not fix either,
 * because every retype hit the same rule. So there is no relative mode now,
 * and a fragment that is not an equation ("*2") is unparseable rather than
 * quietly meaningful.
 *
 * Emptying the box is how you unassign, so blank means zero — NOT "leave it
 * alone". Three cells write assignments (the grid row, the multi-month
 * sheet, the cards strip) and the rule was written inline twice and omitted
 * in the third, where clearing the box silently kept the old amount.
 *
 * NaN is reserved for text that cannot be parsed at all — callers must guard
 * on it rather than book a number nobody typed.
 */
export function parseAssignmentCommit(value: string): number {
  if (value.trim() === '') return 0
  if (isAmountExpression(value)) {
    const cents = evaluateExpressionCents(value)
    return cents === null ? NaN : cents / 100
  }
  return parseMoney(value)
}
