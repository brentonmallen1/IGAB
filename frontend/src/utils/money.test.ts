import { describe, expect, it } from 'vitest'
import { parseAmountInput, sumToCents, toCents } from './money'

describe('parseAmountInput', () => {
  it('parses plain decimal amounts', () => {
    expect(parseAmountInput('12.34')).toBe(12.34)
    expect(parseAmountInput('0.01')).toBe(0.01)
    expect(parseAmountInput('100')).toBe(100)
    expect(parseAmountInput('0')).toBe(0)
  })

  it('parses partial decimals as typed', () => {
    expect(parseAmountInput('12.')).toBe(12)
    expect(parseAmountInput('.5')).toBe(0.5)
    expect(parseAmountInput('12.3')).toBe(12.3)
  })

  it('treats a single comma with 1-2 trailing digits as a decimal comma', () => {
    expect(parseAmountInput('12,34')).toBe(12.34)
    expect(parseAmountInput('12,3')).toBe(12.3)
    expect(parseAmountInput('0,99')).toBe(0.99)
  })

  it('treats commas as grouping when a dot is present or 3 digits follow', () => {
    expect(parseAmountInput('1,234.56')).toBe(1234.56)
    expect(parseAmountInput('1,234')).toBe(1234)
    expect(parseAmountInput('1,234,567')).toBe(1234567)
    expect(parseAmountInput('12,345,678.90')).toBe(12345678.9)
  })

  it('ignores currency symbols and whitespace', () => {
    expect(parseAmountInput('$12.34')).toBe(12.34)
    expect(parseAmountInput(' 12.34 ')).toBe(12.34)
    expect(parseAmountInput('€1,234.56')).toBe(1234.56)
    expect(parseAmountInput('kr 100')).toBe(100)
  })

  it('returns NaN for empty or unparseable input', () => {
    expect(parseAmountInput('')).toBeNaN()
    expect(parseAmountInput('   ')).toBeNaN()
    expect(parseAmountInput('.')).toBeNaN()
    expect(parseAmountInput('abc')).toBeNaN()
    expect(parseAmountInput('1.2.3')).toBeNaN()
  })

  it('rejects negative input — sign is carried by the outflow/inflow field, not the value', () => {
    expect(parseAmountInput('-12.34')).toBeNaN()
    expect(parseAmountInput('12-34')).toBeNaN()
  })

  it('round-trips to exact cents through toCents', () => {
    expect(toCents(parseAmountInput('12.34'))).toBe(1234)
    expect(toCents(parseAmountInput('12,34'))).toBe(1234)
    expect(toCents(parseAmountInput('1,234.56'))).toBe(123456)
    expect(toCents(parseAmountInput('0.1'))).toBe(10)
    expect(toCents(parseAmountInput('999.99'))).toBe(99999)
  })

  it('handles float-hostile values exactly in cents', () => {
    // 1.005 is stored as 1.00499… in IEEE 754, so a third decimal rounds down;
    // real inputs are 2-decimal, this documents the sub-cent edge deterministically
    expect(toCents(parseAmountInput('1.005'))).toBe(100)
    expect(toCents(parseAmountInput('10.999'))).toBe(1100)
    // The classic 999.99 - 999.89 case stays exact when done in cents
    expect(toCents(parseAmountInput('999.99')) - toCents(parseAmountInput('999.89'))).toBe(10)
  })
})

describe('editor amount semantics', () => {
  // Mirrors TransactionEditor.handleSubmit: NaN coalesces to 0, outflow wins
  function editorAmount(outflow: string, inflow: string): number {
    const outflowVal = parseAmountInput(outflow) || 0
    const inflowVal = parseAmountInput(inflow) || 0
    return outflowVal > 0 ? -outflowVal : inflowVal
  }

  it('outflow produces a negative amount', () => {
    expect(editorAmount('12.34', '')).toBe(-12.34)
  })

  it('inflow produces a positive amount', () => {
    expect(editorAmount('', '45.00')).toBe(45)
  })

  it('empty fields produce zero, not NaN', () => {
    expect(editorAmount('', '')).toBe(0)
  })

  it('unparseable input degrades to zero, never NaN into the ledger', () => {
    expect(editorAmount('abc', '')).toBe(0)
    expect(editorAmount('1.2.3', '')).toBe(0)
  })

  it('split totals still validate in integer cents', () => {
    const totalCents = Math.abs(toCents(parseAmountInput('10.00') || 0))
    expect(sumToCents(['3.33', '3.33', '3.34'])).toBe(totalCents)
    expect(sumToCents(['3.33', '3.33', '3.33'])).not.toBe(totalCents)
  })
})
