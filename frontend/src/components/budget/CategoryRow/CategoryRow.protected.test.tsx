/**
 * Interest & fees is kept by the app: the server refuses a rename, so the row
 * offers neither the pencil nor double-click-to-rename — and still offers both
 * on an ordinary envelope.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { makeCategory } from '../../../test-utils/factories'

vi.mock('../../../api/budgets', () => ({
  useBudgets: () => ({ data: [] }),
  useSetAssignment: () => ({ mutate: vi.fn() }),
}))
vi.mock('../../../api/targets', () => ({ useTarget: () => ({ data: null }) }))
vi.mock('../../../api/categories', () => ({ useUpdateCategory: () => ({ mutate: vi.fn() }) }))
vi.mock('../../../stores/uiStore', () => ({
  useUIStore: (sel: (s: unknown) => unknown) =>
    sel({
      selectedCategoryIds: new Set<string>(),
      toggleCategorySelection: vi.fn(),
      selectOnlyCategory: vi.fn(),
      setCategoryInspectorOpen: vi.fn(),
      inspectorUserClosed: false,
      openMobileInspector: vi.fn(),
      budgetRowMode: 'available',
    }),
}))
vi.mock('../../../hooks/useMediaQuery', () => ({ useIsMobile: () => false }))
vi.mock('../CategoryDrag/CategoryDragContext', () => ({ useCategoryDrag: () => null }))
vi.mock('../TargetEditor', () => ({ TargetEditor: () => null }))
vi.mock('../MoveMoneyPopover/MoveMoneyPopover', () => ({ MoveMoneyPopover: () => null }))
vi.mock('../MoveMoneyPopover/MoveMoneyForm', () => ({ MoveMoneyForm: () => null }))
vi.mock('../../transactions/TransactionEditor/TransactionEditor', () => ({
  TransactionEditor: () => null,
}))
vi.mock('../TransactionsPeekModal/TransactionsPeekModal', () => ({
  TransactionsPeekModal: () => null,
}))

import { CategoryRow } from './CategoryRow'

function show(category: ReturnType<typeof makeCategory>) {
  render(<CategoryRow category={category} balance={undefined} budgetId="b1" month="2026-08-01" />)
}

describe('CategoryRow rename', () => {
  it('offers the pencil and double-click on an ordinary envelope', async () => {
    show(makeCategory({ id: 'rent', name: 'Rent' }))

    expect(screen.getByRole('button', { name: 'Rename Rent' })).toBeTruthy()
    await userEvent.dblClick(screen.getByText('Rent'))
    expect(screen.getByDisplayValue('Rent')).toBeTruthy()
  })

  it('offers neither on a protected envelope', async () => {
    show(makeCategory({ id: 'interest', name: 'Interest & fees', is_protected: true }))

    expect(screen.queryByRole('button', { name: /^Rename/ })).toBeNull()
    await userEvent.dblClick(screen.getByText('Interest & fees'))
    expect(screen.queryByDisplayValue('Interest & fees')).toBeNull()
  })
})
