import { describe, expect, it } from 'vitest'
import { abbreviateValue, buildCellMap, intensityPct, maxCellValue } from './seasonalityScale'

const cells = [
  { category_id: 'c1', month: '2026-01-01', total: '120.5' },
  { category_id: 'c1', month: '2026-02-01', total: '80' },
  { category_id: 'c2', month: '2026-01-01', total: '900' },
]

describe('buildCellMap', () => {
  it('keys cells by category and month', () => {
    const map = buildCellMap(cells)
    expect(map.get('c1|2026-01-01')).toBe(120.5)
    expect(map.get('c2|2026-01-01')).toBe(900)
    expect(map.get('c2|2026-02-01')).toBeUndefined()
  })
})

describe('maxCellValue', () => {
  it('finds the hottest cell', () => {
    expect(maxCellValue(cells)).toBe(900)
  })

  it('floors at 1 so an empty grid never divides by zero', () => {
    expect(maxCellValue([])).toBe(1)
  })
})

describe('intensityPct', () => {
  it('scales linearly to the max and rounds', () => {
    expect(intensityPct(450, 900)).toBe(50)
    expect(intensityPct(900, 900)).toBe(100)
  })

  it('caps at 100 even past the max', () => {
    expect(intensityPct(1200, 900)).toBe(100)
  })

  it('is null for empty cells or an empty scale', () => {
    expect(intensityPct(0, 900)).toBeNull()
    expect(intensityPct(10, 0)).toBeNull()
  })
})

describe('abbreviateValue', () => {
  it('renders thousands as k with one decimal', () => {
    expect(abbreviateValue(1234)).toBe('1.2k')
    expect(abbreviateValue(1000)).toBe('1.0k')
  })

  it('renders sub-thousand values as whole numbers', () => {
    expect(abbreviateValue(850.4)).toBe('850')
  })
})
