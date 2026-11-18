/**
 * What a strategy preview promises before you spend real money on it.
 *
 * Two of the strategies SET assigned to a past figure (the history ones) or to
 * zero (Reset Assigned), which unfunds money already spent from an envelope.
 * That is what they are for — and a table of assigned-before/assigned-after is
 * the one place the consequence does not appear, so the preview says it.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { AssignPreviewResponse } from '../../../api/assign'

const applyMock = vi.hoisted(() => vi.fn())
const preview = vi.hoisted(() => ({ current: null as AssignPreviewResponse | null }))
const previewCalls = vi.hoisted(() => [] as string[][])

vi.mock('../../../api/assign', () => ({
  useAssignPreview: (_b: string, _m: string, _s: string, coverIds: string[] = []) => {
    previewCalls.push([...coverIds])
    return { data: preview.current, isLoading: false }
  },
  useAssignApply: () => ({ mutateAsync: applyMock, isPending: false }),
}))
vi.mock('../../../utils/toastUndo', () => ({ useUndoToast: () => vi.fn() }))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))

import { AssignPreviewModal } from './AssignPreviewModal'
import { useAppStore } from '../../../stores/appStore'

beforeEach(async () => {
  // Every test opens a Dialog; drain the deferred history.back() of the last.
  await new Promise((r) => setTimeout(r, 0))
  await new Promise((r) => setTimeout(r, 0))
  window.history.replaceState(null, '')
  applyMock.mockReset()
  previewCalls.length = 0
  useAppStore.setState({ targetCoverMode: 'ask' })
  preview.current = {
    strategy: 'reset_assigned',
    items: [
      {
        category_id: 'c1',
        category_name: 'Groceries',
        current_assigned: 150,
        delta: -150,
        new_assigned: 0,
        target_assigned: null,
        cover_target_assigned: null,
      },
    ],
    total_needed: null,
    to_assign: 0,
    to_return: 150,
    tba_before: 850,
    tba_after: 1000,
    newly_overspent_count: 0,
    newly_overspent_total: 0,
  } as AssignPreviewResponse
})

function open() {
  return render(
    <AssignPreviewModal
      budgetId="b1"
      month="2026-08-01"
      strategy="reset_assigned"
      onClose={vi.fn()}
    />
  )
}

describe('AssignPreviewModal', () => {
  it('says nothing when no envelope ends up in the red', () => {
    open()
    expect(screen.queryByText(/overspent by/)).not.toBeInTheDocument()
  })

  it('names how many envelopes it would push into the red, and by how much', () => {
    preview.current = { ...preview.current!, newly_overspent_count: 1, newly_overspent_total: 130 }
    open()
    expect(screen.getByText(/1 category/)).toBeInTheDocument()
    expect(screen.getByText(/\$130\.00/)).toBeInTheDocument()
    expect(screen.getByText(/Cover Overspending can put it back/)).toBeInTheDocument()
  })

  it('pluralises the count', () => {
    preview.current = { ...preview.current!, newly_overspent_count: 3, newly_overspent_total: 90 }
    open()
    expect(screen.getByText(/3 categories/)).toBeInTheDocument()
  })

  it('keeps the negative-TBA warning separate — different problem, louder tone', () => {
    preview.current = {
      ...preview.current!,
      tba_after: -25,
      newly_overspent_count: 1,
      newly_overspent_total: 130,
    }
    open()
    expect(screen.getByText(/Ready to Assign will go negative/)).toBeInTheDocument()
    expect(screen.getByText(/overspent by/)).toBeInTheDocument()
  })

  it('keeps Apply enabled with nothing to change, and says so instead of applying', () => {
    // It used to be disabled with no reason given; a primary asks and answers.
    preview.current = {
      ...preview.current!,
      items: [{ ...preview.current!.items[0], delta: 0, new_assigned: 150 }],
      to_return: 0,
    }
    open()
    const apply = screen.getByRole('button', { name: /^Apply/ })
    expect(apply).toHaveClass('dialog-btn', 'dialog-btn--primary')
    expect(apply).toBeEnabled()
    fireEvent.click(apply)
    expect(screen.getByRole('alert')).toHaveTextContent(/nothing to apply/)
    expect(screen.getByRole('alert')).toHaveClass('dialog-form__error')
    expect(applyMock).not.toHaveBeenCalled()
  })

  it('shares the footer row and buttons with every dialog', () => {
    open()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass('dialog-btn--secondary')
    expect(screen.getByRole('button', { name: 'Cancel' }).closest('.dialog-actions')).toHaveClass(
      'preview-dialog__actions'
    )
  })
})

describe('AssignPreviewModal: Target Amount with Cover + target', () => {
  const row = (
    id: string,
    name: string,
    current: number,
    target: number,
    cover: number | null,
    covered = false
  ) => {
    const next = covered && cover !== null ? cover : target
    return {
      category_id: id,
      category_name: name,
      current_assigned: current,
      delta: next - current,
      new_assigned: next,
      target_assigned: cover === null ? null : target,
      cover_target_assigned: cover,
    }
  }

  function openTarget() {
    preview.current = {
      ...preview.current!,
      strategy: 'target_amount',
      items: [
        row('groceries', 'Groceries', 30, 100, 130),
        row('dining', 'Dining', 0, 100, 130),
        row('rent', 'Rent', 0, 100, null),
      ],
    }
    return render(
      <AssignPreviewModal
        budgetId="b1"
        month="2026-07-01"
        strategy="target_amount"
        onClose={vi.fn()}
      />
    )
  }

  it('offers the choice on the overspent rows only, starting on Target under Ask', () => {
    openTarget()
    expect(screen.getByRole('radiogroup', { name: 'Groceries' })).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: 'Dining' })).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Rent' })).not.toBeInTheDocument()
    const groceries = screen.getByRole('radiogroup', { name: 'Groceries' })
    expect(within(groceries).getByRole('radio', { name: /^Target/ })).toHaveAttribute(
      'aria-checked',
      'true'
    )
    expect(previewCalls.at(-1)).toEqual([])
  })

  it('asks the server again with the row covered, and applies the same cover_ids', async () => {
    openTarget()
    fireEvent.click(
      within(screen.getByRole('radiogroup', { name: 'Dining' })).getByRole('radio', {
        name: /Cover \+ target/,
      })
    )
    expect(previewCalls.at(-1)).toEqual(['dining'])

    applyMock.mockResolvedValue({
      to_assign: 0,
      to_return: 0,
      categories_changed: 0,
      tba_after: 0,
      batch_id: null,
    })
    fireEvent.click(screen.getByRole('button', { name: /^Apply/ }))
    await vi.waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1))
    expect(applyMock.mock.calls[0][0]).toEqual({
      month: '2026-07-01',
      strategy: 'target_amount',
      cover_ids: ['dining'],
    })
  })

  it('defaults every offered row to Cover + target under that setting', () => {
    useAppStore.setState({ targetCoverMode: 'cover' })
    openTarget()
    expect(previewCalls.at(-1)).toEqual(['dining', 'groceries'])
    expect(
      within(screen.getByRole('radiogroup', { name: 'Groceries' })).getByRole('radio', {
        name: /Cover \+ target/,
      })
    ).toHaveAttribute('aria-checked', 'true')
  })

  it('"same for all" sets every offered row', () => {
    openTarget()
    fireEvent.click(
      within(
        screen.getByRole('radiogroup', { name: 'Same for all overspent categories' })
      ).getByRole('radio', { name: /Cover \+ target/ })
    )
    expect(previewCalls.at(-1)).toEqual(['dining', 'groceries'])
  })
})
