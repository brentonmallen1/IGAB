import { describe, expect, it } from 'vitest'
import { ageDays, ageLabel } from './age'

const NOW = Date.parse('2026-09-18T12:00:00Z')

describe('ageLabel', () => {
  it('says today inside the first day', () => {
    expect(ageLabel('2026-09-18T01:00:00Z', NOW)).toBe('today')
  })

  it('says yesterday, not "1 days ago"', () => {
    expect(ageLabel('2026-09-17T06:00:00Z', NOW)).toBe('yesterday')
  })

  it('counts whole days after that', () => {
    expect(ageLabel('2026-09-06T12:00:00Z', NOW)).toBe('12 days ago')
  })

  it('never goes negative for a clock that is slightly ahead', () => {
    expect(ageDays('2026-09-18T12:00:05Z', NOW)).toBe(0)
  })
})
