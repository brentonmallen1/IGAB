/**
 * The editor's amount, and the difference between "blank" and "not a number".
 *
 * Both used to be zero. The editor's Save was never gated on the amount, so
 * unparseable text in a box saved $0.00 — over an existing row, silently,
 * which is the one thing a budgeting app must never do with money someone
 * already recorded.
 */
import { describe, expect, it } from 'vitest'
import { editorAmount } from './editorAmount'

describe('editorAmount', () => {
  it('reads an outflow as negative cents', () => {
    expect(editorAmount('41.80', '')).toEqual({ cents: -4180, dollars: -41.8 })
  })

  it('reads an inflow as positive cents', () => {
    expect(editorAmount('', '1200')).toEqual({ cents: 120000, dollars: 1200 })
  })

  it('evaluates an expression, because the boxes are calculators', () => {
    expect(editorAmount('12.50 + 3', '')?.cents).toBe(-1550)
  })

  it('reads a typed thousands separator as the number it looks like', () => {
    // parseFloat("1,250") is 1. The shared separator rule is money.ts.
    expect(editorAmount('1,250', '')?.cents).toBe(-125000)
  })

  it('prefers the outflow when both are filled', () => {
    expect(editorAmount('40', '10')?.cents).toBe(-4000)
  })

  it('prefers a real inflow over an outflow of zero', () => {
    // `outflow || inflow` picked the string "0" here, so the editor
    // validated one number and wrote another.
    expect(editorAmount('0', '50')?.cents).toBe(5000)
  })

  it('treats both boxes blank as zero, not as an error', () => {
    // The receipt worker files a $0 stub when a scan exhausts its retries.
    // Reviewing that stub to fix its payee must not be blocked by its
    // own amount.
    expect(editorAmount('', '')).toEqual({ cents: 0, dollars: 0 })
  })

  it.each([
    ['an expression that never evaluated', '12 +'],
    ['a bare minus, because sign is which box you are in', '-5'],
    ['a second decimal point', '1.2.3'],
    ['words', 'lunch'],
  ])('refuses %s rather than calling it zero', (_why, typed) => {
    expect(editorAmount(typed, '')).toBeNull()
  })

  it('still reads through a stray character, which is money.ts being lenient', () => {
    // Where the boundary actually is. `parseAmountInput` strips anything
    // that is not a digit or a point, so a typo next to the digits is a
    // wrong amount rather than a refused one — that is its rule, not this
    // module's, and it is written here so the next reader does not assume
    // this function catches typos.
    expect(editorAmount('4l.80', '')?.cents).toBe(-480)
  })

  it('refuses unparseable text in the other box too', () => {
    expect(editorAmount('', 'abc')).toBeNull()
  })
})
