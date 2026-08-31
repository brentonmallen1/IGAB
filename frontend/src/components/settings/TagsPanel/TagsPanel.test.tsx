import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const updateMutate = vi.hoisted(() => vi.fn((_p: Record<string, unknown>) => Promise.resolve({})))
const TAGS = vi.hoisted(() => [
  {
    id: 'sys',
    name: 'Savings',
    system_key: 'savings',
    color_slot: 'green',
    category_count: 2,
    payee_count: 0,
  },
  {
    id: 'mine',
    name: 'Holiday',
    system_key: null,
    color_slot: 'pink',
    category_count: 0,
    payee_count: 1,
  },
])
vi.mock('../../../api/tags', () => ({
  useTags: () => ({ data: TAGS, isLoading: false }),
  useCreateTag: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateTag: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteTag: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

import { TagsPanel } from './TagsPanel'

describe('TagsPanel system tags', () => {
  beforeEach(() => updateMutate.mockClear())

  it('lets a system tag change colour but not name', async () => {
    render(<TagsPanel budgetId="b1" />)
    fireEvent.click(screen.getAllByText('Edit')[0])

    expect(screen.queryByPlaceholderText('Tag name')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Savings — name is fixed')).toHaveTextContent('Savings')

    // The add-tag form below has its own swatches; the edit row's come first.
    fireEvent.click(screen.getAllByTitle('purple')[0])
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1))
    expect(updateMutate.mock.calls[0][0]).toEqual({ id: 'sys', color_slot: 'purple' })
  })

  it('still lets the user rename their own tags', async () => {
    render(<TagsPanel budgetId="b1" />)
    fireEvent.click(screen.getAllByText('Edit')[1])

    const input = screen.getByPlaceholderText('Tag name')
    fireEvent.change(input, { target: { value: 'Holidays' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1))
    expect(updateMutate.mock.calls[0][0]).toEqual({
      id: 'mine',
      name: 'Holidays',
      color_slot: 'pink',
    })
  })
})
