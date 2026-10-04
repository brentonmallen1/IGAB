import { describe, expect, it, vi } from 'vitest'
import { historyModeToggleOutcome } from './historyModeToggle'

const deps = (answer: boolean) => ({
  confirm: vi.fn().mockResolvedValue(answer),
  importMonth: 'October 2026',
})

describe('the edit-earlier-months switch', () => {
  it('asks before re-deriving, and says the figures will stop matching YNAB', async () => {
    const d = deps(true)
    expect(await historyModeToggleOutcome(true, d)).toBe('rederived')
    const asked = d.confirm.mock.calls[0][0]
    expect(asked.message).toMatch(/stop matching YNAB/)
    expect(asked.message).toMatch(/before October 2026/)
  })

  it('asks before going back, and says earlier edits stop counting', async () => {
    const d = deps(true)
    expect(await historyModeToggleOutcome(false, d)).toBe('anchored')
    expect(d.confirm.mock.calls[0][0].message).toMatch(/no longer counts/)
  })

  it('sends nothing when the person says no', async () => {
    expect(await historyModeToggleOutcome(true, deps(false))).toBeNull()
    expect(await historyModeToggleOutcome(false, deps(false))).toBeNull()
  })
})
