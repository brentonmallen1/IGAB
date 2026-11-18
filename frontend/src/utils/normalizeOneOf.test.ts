import { describe, expect, it } from 'vitest'
import { normalizeOneOf } from './normalizeOneOf'

const MODES = ['full', 'available', 'none'] as const

describe('normalizeOneOf', () => {
  it('keeps a value that is on the list', () => {
    for (const mode of MODES) expect(normalizeOneOf(MODES, mode, 'full')).toBe(mode)
  })

  it('reads anything else as the fallback', () => {
    for (const junk of ['mono', 'FULL', '', 1, null, undefined, {}, ['full']]) {
      expect(normalizeOneOf(MODES, junk, 'available')).toBe('available')
    }
  })
})
