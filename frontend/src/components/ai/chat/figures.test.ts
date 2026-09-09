/**
 * One rule, two languages.
 *
 * The `shared/money_figures.json` block runs the same cases the backend runs
 * in `backend/tests/unit/test_ai_grounding.py`. The renderer styles the
 * figures the grounding check verifies; a regex changed on one side only
 * fails on the other.
 */
import { describe, expect, it } from 'vitest'
import { extractFigures, normalizeFigures } from './figures'
import cases from '../../../../../shared/money_figures.json'

describe('agreement with the backend extractor', () => {
  for (const c of cases.cases) {
    it(c.note, () => {
      expect(extractFigures(c.text)).toEqual(c.figures)
    })
  }
})

describe('normalizeFigures', () => {
  it('repairs the symbol-alone code span gemma writes', () => {
    expect(normalizeFigures('*   **Harborstone**: `$`4,182.33`')).toBe(
      '*   **Harborstone**: `$4,182.33`'
    )
  })

  it('repairs it without the trailing backtick too', () => {
    expect(normalizeFigures('paid `$`42.00 today')).toBe('paid `$42.00` today')
  })

  it('wraps a bare amount', () => {
    expect(normalizeFigures('Groceries was $412.80 in September')).toBe(
      'Groceries was `$412.80` in September'
    )
  })

  it('leaves an amount already in a code span alone', () => {
    expect(normalizeFigures('Groceries was `$412.80`')).toBe('Groceries was `$412.80`')
  })

  it('keeps bold outside the span so both render', () => {
    expect(normalizeFigures('over by **$42.00**')).toBe('over by **`$42.00`**')
  })

  it('does not touch fenced code', () => {
    const block = '```\ntotal: $12.00\n```'
    expect(normalizeFigures(block)).toBe(block)
  })

  it('does not touch counts, years or rates', () => {
    const text = 'In 2026 you had 12 transactions, 32% of income'
    expect(normalizeFigures(text)).toBe(text)
  })

  it('handles an amount at the start of the text', () => {
    expect(normalizeFigures('$5.00 left')).toBe('`$5.00` left')
  })
})
