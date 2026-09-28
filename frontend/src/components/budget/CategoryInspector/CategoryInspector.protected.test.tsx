/**
 * Interest & fees is kept by the app: the server refuses to archive or delete
 * it, so the inspector says so instead of drawing buttons that can only fail —
 * for a selection that includes it, however many others are with it.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeCategory } from '../../../test-utils/factories'

const state = vi.hoisted(() => ({ selected: new Set<string>(), categories: [] as unknown[] }))

vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (sel: (s: unknown) => unknown) =>
    sel({
      selectedCategoryIds: state.selected,
      categoryInspectorOpen: true,
      setCategoryInspectorOpen: vi.fn(),
      clearCategorySelection: vi.fn(),
    }),
}))
vi.mock('../../../stores/appStore', () => ({
  useAppStore: (sel: (s: unknown) => unknown) => sel({ selectedMonth: '2026-08-01' }),
}))
vi.mock('../../../api/budgets', () => ({ useBudgetMonth: () => ({ data: undefined }) }))
vi.mock('../../../api/categories', () => ({
  useCategories: () => ({ data: state.categories }),
  useArchiveCategories: () => ({ mutateAsync: vi.fn() }),
  useUnarchiveCategories: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../DeleteCategoryModal/useDeleteCategoryFlow', () => ({
  useDeleteCategoryFlow: () => ({ requestDelete: vi.fn(), modal: null }),
}))
// The sections are their own components; this file is about the manage bar.
vi.mock('./AvailableBreakdown', () => ({ AvailableBreakdown: () => null }))
vi.mock('./TargetSection', () => ({ TargetSection: () => null }))
vi.mock('./AutoAssignSection', () => ({ AutoAssignSection: () => null }))
vi.mock('./CategoryNotesSection', () => ({ CategoryNotesSection: () => null }))
vi.mock('./CategorySubtitleSection', () => ({ CategorySubtitleSection: () => null }))
vi.mock('./TagsSection', () => ({ TagsSection: () => null }))
vi.mock('./HistorySection', () => ({ HistorySection: () => null }))
vi.mock('./ClassificationSection', () => ({ ClassificationSection: () => null }))
vi.mock('./MonthSummary', () => ({ MonthSummary: () => null }))

import { CategoryInspector } from './CategoryInspector'

const interest = makeCategory({ id: 'interest', name: 'Interest & fees', is_protected: true })
const rent = makeCategory({ id: 'rent', name: 'Rent' })

function show(selected: string[]) {
  state.categories = [interest, rent]
  state.selected = new Set(selected)
  render(<CategoryInspector budgetId="b1" />)
}

describe('CategoryInspector manage bar', () => {
  it('offers archive and delete on an ordinary envelope', () => {
    show(['rent'])

    expect(screen.getByRole('button', { name: /archive/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /delete/i })).toBeTruthy()
  })

  it('says a protected envelope is kept by the app, and offers no buttons', () => {
    show(['interest'])

    expect(screen.getByText(/Interest & fees is kept by the app/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /archive/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
  })

  it('withholds the bulk buttons while a protected envelope is in the selection', () => {
    show(['interest', 'rent'])

    expect(screen.getByText(/Deselect it to manage the rest/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /archive/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
  })
})
