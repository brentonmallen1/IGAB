import { describe, expect, it } from 'vitest'
import { abbreviateValue, buildCellMap, intensityPct, maxCellValue } from './seasonalityScale'
import { PRIVACY_MASK } from '../../../utils/money'
import { compactMoney } from '../../../utils/moneyAxis'

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
  it("is the axes' compact money without the symbol", () => {
    expect(abbreviateValue(1234, false)).toBe('1.2k')
    expect(abbreviateValue(850.4, false)).toBe('850')
    for (const v of [850.4, 1000, 1234, 12_345, 2_400_000]) {
      expect(abbreviateValue(v, false)).toBe(compactMoney(v, ''))
    }
  })

  it('rounds the way the axis beside it does', () => {
    // Its own formatter said "1.0k" and "12.3k" where the axis said 1k, 12k.
    expect(abbreviateValue(1000, false)).toBe('1k')
    expect(abbreviateValue(12_345, false)).toBe('12k')
  })

  it('scales past a million instead of counting thousands forever', () => {
    // It printed "2400.0k".
    expect(abbreviateValue(2_400_000, false)).toBe('2.4M')
  })
})

/**
 * The Seasonality heatmap and the Plan vs Reality matrix draw their own cell
 * labels, so neither went through `useFormatters` and both printed real
 * amounts with privacy mode on — whose whole purpose is that "sign and digits
 * hidden, so overspending can't be inferred".
 *
 * `masked` is a required parameter rather than a store read, so this module
 * stays pure and the branch is a one-line test — and required, so a caller
 * cannot print real amounts by leaving it out.
 */
describe('abbreviateValue masks for privacy mode', () => {
  it('hides the digits when masked', () => {
    expect(abbreviateValue(4180, true)).toBe(PRIVACY_MASK)
    expect(abbreviateValue(4180, true)).not.toContain('4')
  })
})
