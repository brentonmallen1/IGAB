import { describe, expect, it } from 'vitest'
import { formatBytes } from './formatBytes'

describe('formatBytes', () => {
  it('counts plain bytes below a kilobyte', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1023)).toBe('1023 B')
  })

  it('steps up at each binary boundary', () => {
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1024 ** 2)).toBe('1.0 MB')
    expect(formatBytes(1024 ** 3)).toBe('1.00 GB')
  })

  it('carries a big archive up to GB — the snapshots panel stopped at MB', () => {
    // 3 GiB read as "3072.0 MB" in BudgetSnapshotsPanel's copy.
    expect(formatBytes(3 * 1024 ** 3)).toBe('3.00 GB')
  })

  it('keeps a decimal in MB — the AI panel rounded them away', () => {
    // Two models a few hundred KB apart both rendered "31 MB".
    expect(formatBytes(31.2 * 1024 ** 2)).toBe('31.2 MB')
    expect(formatBytes(31.8 * 1024 ** 2)).toBe('31.8 MB')
  })

  it('does not print NaN at a reader', () => {
    expect(formatBytes(Number.NaN)).toBe('—')
  })
})
