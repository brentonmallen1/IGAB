import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

/**
 * The two old copies stay gone. `.upcoming-row` was the register's and
 * `.sched-table__row` the page's; a stylesheet that grows either back has
 * reintroduced the second implementation.
 */
const SRC = join(dirname(fileURLToPath(import.meta.url)), '../../..')

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return files(full)
    return /\.(css|tsx)$/.test(full) && !full.endsWith('.test.ts') ? [full] : []
  })
}

describe('a scheduled transaction is drawn by ScheduledRow only', () => {
  it.each(['upcoming-row', 'sched-table__row', 'sched-cell--'])('%s appears nowhere', (name) => {
    const hits = files(SRC).filter((f) => readFileSync(f, 'utf8').includes(name))
    expect(hits).toEqual([])
  })
})
