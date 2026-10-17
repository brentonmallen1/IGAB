/**
 * The target editor's "Stop at" field and its Suggest row.
 *
 * The chips are served figures (`useTargetSuggestions`); what they fill, and
 * which shapes take a stop, are `targetSuggestions.ts` and `targetForm.ts`.
 * This holds the wiring: a chip writes its field, the stop is sent, and it
 * goes away for a savings balance.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { TargetEditor } from './TargetEditor'
import { useAppStore } from '../../stores/appStore'
import type { CategoryTarget, TargetSuggestions } from '../../types'

const upsert = vi.fn()
let suggestions: TargetSuggestions | undefined

vi.mock('../../api/targets', () => ({
  useUpsertTarget: () => ({ mutateAsync: upsert, isPending: false }),
  useDeleteTarget: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTargetSuggestions: () => ({ data: suggestions }),
}))

const SERVED: TargetSuggestions = {
  category_id: 'c1',
  average_spent: 210,
  peak_spent: 480,
  peak_spent_month: '2026-03-01',
  peak_available: 900,
  peak_available_month: '2026-06-01',
  months_counted: 12,
}

function open(existing: CategoryTarget | null = null) {
  render(
    <TargetEditor
      categoryId="c1"
      categoryName="Car repairs"
      existing={existing}
      onClose={vi.fn()}
    />
  )
}

const amount = () => screen.getByLabelText('Amount') as HTMLInputElement
const stopAt = () => screen.queryByLabelText('Stop at (optional)') as HTMLInputElement | null

beforeEach(() => {
  upsert.mockReset()
  suggestions = SERVED
  useAppStore.setState({ currentBudgetId: 'b1' })
})

describe('the Suggest row', () => {
  it('fills the amount from a spending chip and the stop from the balance chip', () => {
    open()
    fireEvent.click(screen.getByRole('button', { name: /^Avg .*\/mo/ }))
    expect(amount().value).toBe('210.00')
    fireEvent.click(screen.getByRole('button', { name: /^Peak month/ }))
    expect(amount().value).toBe('480.00')
    fireEvent.click(screen.getByRole('button', { name: /^Peak balance/ }))
    expect(stopAt()!.value).toBe('900.00')
    expect(amount().value).toBe('480.00')
  })

  it('draws nothing when there is nothing to suggest', () => {
    suggestions = { ...SERVED, months_counted: 0 }
    open()
    expect(screen.queryByRole('group', { name: 'Suggested amounts' })).toBeNull()
  })
})

describe('Stop at', () => {
  it('is sent with a monthly target', async () => {
    open()
    fireEvent.change(amount(), { target: { value: '100' } })
    fireEvent.change(stopAt()!, { target: { value: '1000' } })
    fireEvent.submit(document.querySelector('form.dialog-form')!)
    await vi.waitFor(() => expect(upsert).toHaveBeenCalled())
    expect(upsert.mock.calls[0][0]).toMatchObject({
      target_type: 'monthly_funding',
      target_amount: 100,
      target_limit: 1000,
    })
  })

  it('opens holding the stop already saved', () => {
    open({
      id: 't1',
      category_id: 'c1',
      target_type: 'monthly_funding',
      target_amount: 100,
      target_date: null,
      check_after_day: null,
      weekday: null,
      target_limit: 1000,
    })
    expect(stopAt()!.value).toBe('1000')
  })

  it('is not offered on a savings balance, and the balance chip fills its amount', () => {
    open()
    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'savings_balance' } })
    expect(stopAt()).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^Peak balance/ }))
    expect(amount().value).toBe('900.00')
  })
})
