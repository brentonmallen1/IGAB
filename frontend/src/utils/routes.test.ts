import { describe, expect, it } from 'vitest'
import { parentRoute } from './routes'

describe('parentRoute', () => {
  it.each([
    ['/accounts/abc-123', '/accounts'],
    ['/liabilities/abc-123', '/liabilities'],
    ['/assets/abc-123', '/assets'],
    ['/settings/budget', '/settings'],
    ['/system/simplefin', '/system'],
    ['/system', '/settings'],
    ['/settings', '/budget'],
    ['/accounts', '/budget'],
    ['/reports', '/budget'],
    ['/budget', '/budget'],
  ])('%s → %s', (from, to) => {
    expect(parentRoute(from)).toBe(to)
  })
})
