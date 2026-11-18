/**
 * Target Amount over several envelopes, some of them overspent: the device's
 * `targetCoverMode` decides whether to ask Target or Cover + target, and the
 * question lists only the envelopes the server offers it on.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CategoryBalance } from '../../../types'
import type { TargetCoverMode } from '../../../utils/targetCover'
import { makeCategory } from '../../../test-utils/factories'

const state = vi.hoisted(() => ({
  mode: 'ask' as TargetCoverMode,
  balances: [] as unknown[],
}))
const mutate = vi.hoisted(() => vi.fn())
const mutateAsync = vi.hoisted(() => vi.fn())

vi.mock('../../../stores/appStore', () => ({
  useAppStore: (sel: (s: unknown) => unknown) =>
    sel({ selectedMonth: '2026-07-01', targetCoverMode: state.mode }),
}))
vi.mock('../../../api/budgets', () => ({
  useBudgetMonth: () => ({ data: { category_balances: state.balances } }),
}))
vi.mock('../../../api/categoryHistory', () => ({
  useCategoryHistoryBatch: () => ({ data: [] }),
  useAutoAssign: () => ({ mutate, mutateAsync, isPending: false }),
}))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({
    data: [
      makeCategory({ id: 'groceries', name: 'Groceries' }),
      makeCategory({ id: 'dining', name: 'Dining' }),
      makeCategory({ id: 'rent', name: 'Rent' }),
    ],
  }),
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))

import { AutoAssignSection } from './AutoAssignSection'

const balance = (category_id: string, target: number | null, cover: number | null) =>
  ({
    category_id,
    target_assigned: target,
    cover_target_assigned: cover,
  }) as unknown as CategoryBalance

beforeEach(async () => {
  // Some tests open a Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  mutate.mockReset()
  mutateAsync.mockReset().mockResolvedValue(undefined)
  state.mode = 'ask'
  // Groceries (case A) and Dining (case C) are overspent; Rent is not.
  state.balances = [
    balance('groceries', 100, 130),
    balance('dining', 100, 130),
    balance('rent', 100, null),
  ]
})

const ALL = ['groceries', 'dining', 'rent']

function pressTarget(ids: string[]) {
  render(<AutoAssignSection categoryIds={ids} budgetId="b1" />)
  fireEvent.click(screen.getByRole('button', { name: /Target Amount/ }))
}

describe('AutoAssignSection: Cover + target', () => {
  it('asks, listing only the overspent categories', () => {
    pressTarget(ALL)

    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('radiogroup', { name: 'Groceries' })).toBeInTheDocument()
    expect(within(dialog).getByRole('radiogroup', { name: 'Dining' })).toBeInTheDocument()
    expect(within(dialog).queryByRole('radiogroup', { name: 'Rent' })).not.toBeInTheDocument()
    expect(within(dialog).getByText(/1 other category takes its target amount/)).toBeTruthy()
    expect(mutate).not.toHaveBeenCalled()
  })

  it('sends the per-row choice as cover_ids, with the figures it sets', async () => {
    pressTarget(ALL)
    const dialog = screen.getByRole('dialog')
    fireEvent.click(
      within(within(dialog).getByRole('radiogroup', { name: 'Dining' })).getByRole('radio', {
        name: /Cover \+ target/,
      })
    )
    fireEvent.click(within(dialog).getByRole('button', { name: 'Assign targets' }))

    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
    const sent = mutateAsync.mock.calls[0][0]
    expect(sent.action).toBe('target_amount')
    expect(sent.categoryIds).toEqual(ALL)
    expect(sent.coverIds).toEqual(['dining'])
    expect(sent.amounts).toEqual(
      new Map([
        ['groceries', 100],
        ['dining', 130],
        ['rent', 100],
      ])
    )
  })

  it('"same for all" picks every row at once', async () => {
    pressTarget(ALL)
    const dialog = screen.getByRole('dialog')
    fireEvent.click(
      within(within(dialog).getByRole('radiogroup', { name: /same for all/ })).getByRole('radio', {
        name: /Cover \+ target/,
      })
    )
    fireEvent.click(within(dialog).getByRole('button', { name: 'Assign targets' }))
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
    expect(mutateAsync.mock.calls[0][0].coverIds).toEqual(['groceries', 'dining'])
  })

  it('"Target only" skips the question and sends no cover_ids', () => {
    state.mode = 'target'
    pressTarget(ALL)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0][0].coverIds).toEqual([])
  })

  it('"Cover + target" skips the question and covers every offered category', () => {
    state.mode = 'cover'
    render(<AutoAssignSection categoryIds={ALL} budgetId="b1" />)
    // The button says what the press sets: 130 + 130 + 100.
    const button = screen.getByRole('button', { name: /Target Amount/ })
    expect(button).toHaveTextContent('$360.00')
    fireEvent.click(button)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mutate.mock.calls[0][0].coverIds).toEqual(['groceries', 'dining'])
  })

  it('does not ask when nothing selected is overspent', () => {
    state.balances = [balance('groceries', 100, null), balance('rent', 100, null)]
    pressTarget(['groceries', 'rent'])
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mutate).toHaveBeenCalledTimes(1)
  })

  it('gives one category its own Cover + target row instead of asking', () => {
    render(<AutoAssignSection categoryIds={['dining']} budgetId="b1" />)
    const cover = screen.getByRole('button', { name: /Cover \+ target/ })
    expect(cover).toHaveTextContent('$130.00')
    fireEvent.click(screen.getByRole('button', { name: /Target Amount/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(cover)
    expect(mutate.mock.calls[1][0]).toMatchObject({
      action: 'target_amount',
      categoryIds: ['dining'],
      coverIds: ['dining'],
      amounts: new Map([['dining', 130]]),
    })
  })

  it('offers no Cover + target row to a category that is not overspent', () => {
    render(<AutoAssignSection categoryIds={['rent']} budgetId="b1" />)
    expect(screen.queryByRole('button', { name: /Cover \+ target/ })).not.toBeInTheDocument()
  })
})
