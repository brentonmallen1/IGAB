import { describe, expect, it, vi } from 'vitest'
import { historyModeToggleOutcome } from './historyModeToggle'

const deps = (answer: boolean, keepsHistory = true) => ({
  confirm: vi.fn().mockResolvedValue(answer),
  importMonth: 'October 2026',
  keepsHistory,
})

describe('the edit-earlier-months switch', () => {
  it('asks before re-deriving, and says the figures will stop matching YNAB', async () => {
    const d = deps(true)
    expect(await historyModeToggleOutcome(true, d)).toBe('rederived')
    const asked = d.confirm.mock.calls[0][0]
    expect(asked.message).toMatch(/stop matching YNAB/)
    expect(asked.message).toMatch(/before October 2026/)
    expect(asked.message).toMatch(/Only do this if you need to change/)
    expect(asked.message).toMatch(/aren't bugs/)
  })

  it("points at the read-only view only where the import kept YNAB's figures", async () => {
    const kept = deps(true, true)
    await historyModeToggleOutcome(true, kept)
    expect(kept.confirm.mock.calls[0][0].message).toMatch(/read-only, as YNAB showed them/)

    // An import from before the figures were kept has nothing to look back at.
    const older = deps(true, false)
    await historyModeToggleOutcome(true, older)
    expect(older.confirm.mock.calls[0][0].message).not.toMatch(/read-only/)
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
