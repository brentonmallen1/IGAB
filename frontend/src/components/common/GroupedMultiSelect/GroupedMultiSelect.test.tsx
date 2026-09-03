import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GroupedMultiSelect, type MultiSelectOption } from './GroupedMultiSelect'

const OPTIONS: MultiSelectOption[] = [
  { id: 'rent', label: 'Rent', group: 'Monthly Bills' },
  { id: 'power', label: 'Electric', group: 'Monthly Bills' },
  { id: 'water', label: 'Water', group: 'Monthly Bills' },
  { id: 'car', label: 'Car Maintenance', group: 'True Expenses' },
  { id: 'gifts', label: 'Gifts', group: 'True Expenses' },
]

function setup(selectedIds: string[] = []) {
  const onChange = vi.fn()
  const utils = render(
    <GroupedMultiSelect options={OPTIONS} selectedIds={selectedIds} onChange={onChange} />
  )
  const search = utils.container.querySelector('input')!
  return { ...utils, search, onChange }
}

describe('GroupedMultiSelect', () => {
  it('toggles a single option on and off', () => {
    const { onChange } = setup()
    fireEvent.mouseDown(screen.getByText('Rent'))
    expect(onChange).toHaveBeenLastCalledWith(['rent'])

    const { onChange: onChange2 } = setup(['rent', 'power'])
    fireEvent.mouseDown(screen.getAllByText('Rent')[1])
    expect(onChange2).toHaveBeenLastCalledWith(['power'])
  })

  it('a group header selects the whole group, and deselects it once whole', () => {
    const { onChange } = setup()
    fireEvent.mouseDown(screen.getByText('Monthly Bills'))
    expect(onChange).toHaveBeenLastCalledWith(['rent', 'power', 'water'])
  })

  it('a fully selected group deselects only its own members', () => {
    const { onChange } = setup(['rent', 'power', 'water', 'car'])
    fireEvent.mouseDown(screen.getByText('Monthly Bills'))
    expect(onChange).toHaveBeenLastCalledWith(['car'])
  })

  it('shows a tri-state group header — partial is neither checked nor clear', () => {
    const { container } = setup(['rent'])
    const headers = container.querySelectorAll('.gms__group-header')
    expect(headers[0].className).toContain('--partial')
    expect(headers[0].className).not.toContain('--selected')
    // and the tally says how far in the group has come
    expect(headers[0].textContent).toContain('1/3')
  })

  it('search filters the list and empties groups that no longer match', () => {
    const { search, container } = setup()
    fireEvent.change(search, { target: { value: 'wat' } })
    expect(container.querySelectorAll('.gms__option')).toHaveLength(1)
    expect(screen.getByText('Water')).toBeTruthy()
    expect(screen.queryByText('True Expenses')).toBeNull()
  })

  it('reports no results rather than an empty box', () => {
    const { search } = setup()
    fireEvent.change(search, { target: { value: 'zzz' } })
    expect(screen.getByText('No results')).toBeTruthy()
  })

  it('Select all takes every option — including ones filtered out of view', () => {
    const { search, onChange } = setup()
    fireEvent.change(search, { target: { value: 'wat' } })
    fireEvent.mouseDown(screen.getByText('Select all'))
    expect(onChange).toHaveBeenLastCalledWith(['rent', 'power', 'water', 'car', 'gifts'])
  })

  it('Clear all empties the selection, and is the inverse the old checkbox grid lacked', () => {
    const { onChange } = setup(['rent', 'car'])
    fireEvent.mouseDown(screen.getByText('Clear all'))
    expect(onChange).toHaveBeenLastCalledWith([])
  })

  it('hides Select all once everything is selected', () => {
    setup(OPTIONS.map((o) => o.id))
    expect(screen.queryByText('Select all')).toBeNull()
    expect(screen.getByText('Clear all')).toBeTruthy()
  })

  it('counts the selection', () => {
    setup(['rent', 'car'])
    expect(screen.getByText('2 selected')).toBeTruthy()
  })

  it('arrow keys move the highlight and Enter toggles it', () => {
    const { search, onChange } = setup()
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChange).toHaveBeenLastCalledWith(['water'])
  })

  it('keyboard navigation walks the filtered list, not the full one', () => {
    const { search, onChange } = setup()
    fireEvent.change(search, { target: { value: 'e' } }) // Rent, Electric, Car Maintenance, Gifts
    fireEvent.keyDown(search, { key: 'ArrowDown' })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onChange).toHaveBeenLastCalledWith(['power'])
  })

  it('Escape hands the dismissal to the host', () => {
    const onEscape = vi.fn()
    const { container } = render(
      <GroupedMultiSelect
        options={OPTIONS}
        selectedIds={[]}
        onChange={vi.fn()}
        onEscape={onEscape}
      />
    )
    fireEvent.keyDown(container.querySelector('input')!, { key: 'Escape' })
    expect(onEscape).toHaveBeenCalled()
  })

  it('the list is a scroll-list, so a long budget cannot grow the panel', () => {
    const { container } = setup()
    expect(container.querySelector('.gms__list')!.className).toContain('scroll-list')
  })
})
