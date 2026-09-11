import { describe, expect, it } from 'vitest'
import { tileFontSize, tileLabel } from './treemapTile'

describe('tileLabel', () => {
  it('cuts by the rule every chart shares, not one character wider', () => {
    // A 112px tile fits 16 characters. The tile's own copy kept `16 - 1` and
    // read "Harborstone Uti…" where Volatility, at 16, read "Harborstone Ut…".
    expect(tileLabel('Harborstone Utilities', 112)).toBe('Harborstone Ut…')
  })

  it('leaves a name that fits alone', () => {
    expect(tileLabel('Groceries', 112)).toBe('Groceries')
  })
})

describe('tileFontSize', () => {
  it('is 12px until the tile is too narrow for it', () => {
    expect(tileFontSize(200)).toBe(12)
    expect(tileFontSize(70)).toBe(10)
  })
})
