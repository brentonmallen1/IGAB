/**
 * Bulk-flow tests: the floating selection bar is the entry point for bulk
 * categorize / clear / delete, so its wiring must hit the right handler with
 * the right arguments — a miswired button rewrites many transactions at once.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SelectionActionBar } from './SelectionActionBar'

const CATEGORY_OPTIONS = [
  { id: 'cat-1', label: 'Groceries', group: 'Everyday' },
  { id: 'cat-2', label: 'Fun', group: 'Everyday' },
]

const handlers = {
  onCategorize: vi.fn(),
  onSetCleared: vi.fn(),
  onDelete: vi.fn(),
  onDuplicate: vi.fn(),
  onClear: vi.fn(),
}

function renderBar(props: Partial<Parameters<typeof SelectionActionBar>[0]> = {}) {
  return render(
    <SelectionActionBar
      selectedCount={3}
      selectedTotal={-42.5}
      categoryOptions={CATEGORY_OPTIONS}
      {...handlers}
      {...props}
    />
  )
}

describe('SelectionActionBar bulk flows', () => {
  beforeEach(() => {
    Object.values(handlers).forEach((fn) => fn.mockClear())
  })

  it('shows the selection count and the formatted signed total', () => {
    renderBar()
    expect(screen.getByText('3 Transactions')).toBeInTheDocument()
    expect(screen.getByText('-$42.50')).toBeInTheDocument()
  })

  it('bulk categorize passes the chosen category id', () => {
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: /Categorize/ }))
    // Combobox options select on mousedown
    fireEvent.mouseDown(screen.getByText('Groceries'))
    expect(handlers.onCategorize).toHaveBeenCalledWith('cat-1')
    expect(handlers.onCategorize).toHaveBeenCalledTimes(1)
  })

  it('bulk clear marks selected as cleared', () => {
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: /^Clear$/ }))
    expect(handlers.onSetCleared).toHaveBeenCalledWith('cleared')
  })

  it('bulk delete lives behind the More menu, not one click away', () => {
    renderBar()
    expect(handlers.onDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /More/ }))
    fireEvent.click(screen.getByText('Delete Selected'))
    expect(handlers.onDelete).toHaveBeenCalledTimes(1)
  })

  it('mark-uncleared routes through the More menu', () => {
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: /More/ }))
    fireEvent.click(screen.getByText('Mark Uncleared'))
    expect(handlers.onSetCleared).toHaveBeenCalledWith('uncleared')
  })
})
