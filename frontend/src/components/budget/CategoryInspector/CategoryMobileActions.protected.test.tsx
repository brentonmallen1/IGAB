/**
 * Interest & fees is kept by the app: the server refuses to rename, archive or
 * delete it, so the mobile sheet does not offer those three — and still
 * offers them on an ordinary envelope.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { makeCategory } from '../../../test-utils/factories'

vi.mock('../../../api/categories', () => ({
  useUpdateCategory: () => ({ mutate: vi.fn() }),
  useArchiveCategories: () => ({ mutate: vi.fn() }),
  useUnarchiveCategories: () => ({ mutate: vi.fn() }),
}))
vi.mock('../DeleteCategoryModal/useDeleteCategoryFlow', () => ({
  useDeleteCategoryFlow: () => ({ requestDelete: vi.fn(), modal: null }),
}))

import { CategoryMobileActions } from './CategoryMobileActions'

function show(category: ReturnType<typeof makeCategory>) {
  render(<CategoryMobileActions budgetId="b1" category={category} onDone={vi.fn()} />)
}

describe('CategoryMobileActions', () => {
  it('offers rename, archive and delete on an ordinary envelope', () => {
    show(makeCategory({ id: 'rent', name: 'Rent' }))

    expect(screen.getByRole('button', { name: /rename/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /archive/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /delete/i })).toBeTruthy()
  })

  it('offers none of them on a protected envelope', () => {
    show(makeCategory({ id: 'interest', name: 'Interest & fees', is_protected: true }))

    expect(screen.queryByRole('button', { name: /rename/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /archive/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull()
  })
})
