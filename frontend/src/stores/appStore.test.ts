/**
 * The text-size ladder.
 *
 * It gained two rungs and the names moved down one, which is the kind of
 * change that silently resizes someone's app: a person on "Medium" would have
 * woken up smaller. The migration is what stops that, and the second test is
 * what stops a sixth step being added to the list without a size to go with
 * it — the sizes live in CSS and the names live here.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { FONT_SCALES, useAppStore } from './appStore'
import { PERSIST_KEYS } from './persistKeys'

describe('font scale migration', () => {
  const migrate = useAppStore.persist.getOptions().migrate!

  it('keeps a stored size the size it was when the names shifted', () => {
    // The old three-step ladder: medium was 16px base, large was 18px. Those
    // are this ladder's large and xxlarge.
    expect(migrate({ fontScale: 'medium' }, 0)).toMatchObject({ fontScale: 'large' })
    expect(migrate({ fontScale: 'large' }, 0)).toMatchObject({ fontScale: 'xxlarge' })
  })

  it('leaves small alone — it is the same step it always was', () => {
    expect(migrate({ fontScale: 'small' }, 0)).toMatchObject({ fontScale: 'small' })
  })

  it('does not re-run on state already at the current version', () => {
    expect(migrate({ fontScale: 'medium' }, 1)).toMatchObject({ fontScale: 'medium' })
  })

  it('survives state that never had a font scale', () => {
    expect(() => migrate({ theme: 'dark' }, 0)).not.toThrow()
  })
})

describe('font scale options', () => {
  const BASE_CSS = readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), '../themes/base.css'),
    'utf8'
  )

  it('offers five steps', () => {
    expect(FONT_SCALES.map((s) => s.value)).toEqual([
      'small',
      'medium',
      'large',
      'xlarge',
      'xxlarge',
    ])
  })

  it('every step above the default has a size defined for it', () => {
    // 'small' is the :root ladder itself and sets no override.
    for (const { value } of FONT_SCALES.filter((s) => s.value !== 'small')) {
      expect(BASE_CSS).toContain(`[data-font-size="${value}"]`)
    }
  })

  it('the steps grow, and none of them is a leap', () => {
    const percents = FONT_SCALES.filter((s) => s.value !== 'small').map((s) => {
      const match = BASE_CSS.match(
        new RegExp(`\\[data-font-size="${s.value}"\\]\\s*\\{[^}]*font-size:\\s*(\\d+)%`)
      )
      return Number(match![1])
    })
    expect(percents).toEqual([...percents].sort((a, b) => a - b))
    // The old ladder jumped 14 -> 16px in one step, which is what "Medium
    // feels huge" was. No step here is more than ~8%.
    const gaps = [100, ...percents].slice(1).map((p, i) => p - [100, ...percents][i])
    expect(Math.max(...gaps)).toBeLessThanOrEqual(8)
  })
})

describe('the import-anchor month clamp', () => {
  it('every navigation surface obeys one rule: months before the anchor do not exist', () => {
    useAppStore.getState().setBudgetAnchorMonth('2026-08-01')
    useAppStore.getState().setSelectedMonth('2026-05-01')
    expect(useAppStore.getState().selectedMonth).toBe('2026-08-01')
    useAppStore.getState().setSelectedMonth('2026-09-01')
    expect(useAppStore.getState().selectedMonth).toBe('2026-09-01')
  })

  it('clamps nothing on an unanchored budget', () => {
    useAppStore.getState().setBudgetAnchorMonth(null)
    useAppStore.getState().setSelectedMonth('2020-01-01')
    expect(useAppStore.getState().selectedMonth).toBe('2020-01-01')
  })

  it('is never persisted — the anchor belongs to a budget, not to the device', () => {
    useAppStore.getState().setBudgetAnchorMonth('2026-08-01')
    const stored = JSON.parse(localStorage.getItem(PERSIST_KEYS.app) ?? '{"state":{}}')
    // Relaunching on Transactions or Reports would otherwise clamp every
    // month against a budget that may not even be the open one — BudgetPage,
    // the only page that clears it, has not mounted yet.
    expect(stored.state).not.toHaveProperty('budgetAnchorMonth')
    expect(stored.state.selectedMonth).toBeDefined()
  })

  it('drops when the open budget changes', () => {
    useAppStore.getState().setBudgetAnchorMonth('2026-08-01')
    useAppStore.getState().setCurrentBudgetId('budget-b')
    expect(useAppStore.getState().budgetAnchorMonth).toBeNull()
    useAppStore.getState().setSelectedMonth('2020-01-01')
    expect(useAppStore.getState().selectedMonth).toBe('2020-01-01')
  })

  it('survives re-selecting the budget already open', () => {
    useAppStore.getState().setCurrentBudgetId('budget-a')
    useAppStore.getState().setBudgetAnchorMonth('2026-08-01')
    useAppStore.getState().setCurrentBudgetId('budget-a')
    expect(useAppStore.getState().budgetAnchorMonth).toBe('2026-08-01')
  })

  it('drops when the budget is closed', () => {
    useAppStore.getState().setBudgetAnchorMonth('2026-08-01')
    useAppStore.getState().clearCurrentBudget()
    expect(useAppStore.getState().budgetAnchorMonth).toBeNull()
  })
})
