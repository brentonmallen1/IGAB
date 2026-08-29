/**
 * Arithmetic expression evaluation for amount inputs ("12.50+3.99", "*2").
 *
 * All literals are parsed into integer cents before any arithmetic so binary
 * float artifacts never enter sums (0.1+0.2 is exactly 30 cents here).
 * Multiplication and division may produce fractional cents mid-expression;
 * the result is rounded to a whole cent once, at the end.
 *
 * Relative mode (assignment cells): an expression starting with an operator
 * is applied against a base value — "+50" adds, "*2" doubles, "-25" subtracts.
 */
import { parseAmountInput, parseMoney, toCents } from './money'

type Token =
  | { t: 'num'; v: number } // integer cents
  | { t: 'op'; v: '+' | '-' | '*' | '/' }
  | { t: 'paren'; v: '(' | ')' }

const HAS_OPERATOR = /[+*/()]/

/**
 * Whether the text should be treated as an expression rather than a plain
 * amount. A single leading minus is a sign, not arithmetic — except in
 * relative mode, where every leading operator acts on the base value.
 */
export function isAmountExpression(raw: string, relative = false): boolean {
  const s = raw.trim()
  if (s === '') return false
  if (HAS_OPERATOR.test(s)) return true
  if (s.slice(1).includes('-')) return true
  if (relative && /^[-+*/]/.test(s)) return true
  return false
}

/** Parse one numeric literal into integer cents, or null if malformed. */
function literalToCents(tokenText: string): number | null {
  let normalized: string
  const commas = (tokenText.match(/,/g) ?? []).length
  if (commas === 0) {
    normalized = tokenText
  } else if (tokenText.includes('.')) {
    // Both present: commas are grouping ("1,234.56")
    normalized = tokenText.replace(/,/g, '')
  } else if (commas === 1 && /,\d{1,2}$/.test(tokenText)) {
    // Single comma with 1–2 trailing digits: decimal comma ("12,34")
    normalized = tokenText.replace(',', '.')
  } else {
    normalized = tokenText.replace(/,/g, '')
  }
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

/**
 * Evaluate an amount expression to integer cents, or null if invalid.
 * With baseCents set, a leading operator applies against the base.
 */
export function evaluateExpressionCents(
  raw: string,
  baseCents: number | null = null
): number | null {
  const s = raw.trim()
  if (s === '') return null
  let tokens = tokenize(s)
  if (tokens === null || tokens.length === 0) return null
  if (baseCents !== null && tokens[0].t === 'op') {
    tokens = [{ t: 'num', v: baseCents }, ...tokens]
  }
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
 * Expression-aware cents for validation sums (split remainders). Falls back
 * to toCents so plain-value behavior is unchanged. NaN if the expression is
 * invalid or negative.
 */
export function expressionToCents(value: string): number {
  if (isAmountExpression(value)) {
    const cents = evaluateExpressionCents(value)
    return cents === null || cents < 0 ? NaN : cents
  }
  return toCents(value)
}

/** Sum form inputs exactly in cents, expression-aware (NaN entries count 0). */
export function sumExpressionsToCents(values: string[]): number {
  return values.reduce((sum, v) => {
    const c = expressionToCents(v)
    return sum + (isNaN(c) ? 0 : c)
  }, 0)
}

/**
 * Assignment-cell parse: plain values set the amount absolutely (parseMoney
 * semantics, negatives allowed); a leading operator adjusts the current
 * value ("+50", "*2"). Returns dollars, NaN if invalid.
 */
export function parseAssignmentInput(value: string, baseAmount: number): number {
  if (isAmountExpression(value, true)) {
    const cents = evaluateExpressionCents(value, toCents(baseAmount))
    return cents === null ? NaN : cents / 100
  }
  return parseMoney(value)
}

/**
 * What an assignment cell commits when the user presses Enter or tabs away.
 *
 * Emptying the box is how you unassign, so blank means zero — NOT "leave it
 * alone". Three cells write assignments (the grid row, the multi-month sheet,
 * the cards strip) and the rule was written inline twice and omitted in the
 * third, where clearing the box silently kept the old amount and a leading
 * "+" and any negative were rejected besides: it reached for
 * `parseAmountExpressionInput`, which is built for outflow/inflow fields
 * where the sign is structural.
 *
 * NaN is reserved for text that cannot be parsed at all — callers must guard
 * on it rather than book a number nobody typed.
 */
export function parseAssignmentCommit(value: string, currentAssigned: number): number {
  if (value.trim() === '') return 0
  return parseAssignmentInput(value, currentAssigned)
}
