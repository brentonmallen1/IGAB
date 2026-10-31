import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CategorySearch } from './CategorySearch'
import { useUIStore } from '../../../stores/uiStore'

beforeEach(() => {
  useUIStore.setState({ categorySearch: '' })
})

const input = () => screen.getByRole('searchbox', { name: /Filter categories/ })

describe('CategorySearch', () => {
  it('writes the query to the store the grid reads', () => {
    render(<CategorySearch />)
    fireEvent.change(input(), { target: { value: 'tag:essential' } })
    expect(useUIStore.getState().categorySearch).toBe('tag:essential')
  })

  it('clears from its own button and keeps the focus in the field', () => {
    useUIStore.setState({ categorySearch: 'rent' })
    render(<CategorySearch />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear the filter' }))
    expect(useUIStore.getState().categorySearch).toBe('')
    expect(input()).toHaveFocus()
  })

  // The Tools sheet's copy never cleared on Escape; the bar's did.
  it('clears on Escape, then hands Escape to its caller', () => {
    useUIStore.setState({ categorySearch: 'rent' })
    const onEscape = vi.fn()
    render(<CategorySearch onEscape={onEscape} />)
    fireEvent.keyDown(input(), { key: 'Escape' })
    expect(useUIStore.getState().categorySearch).toBe('')
    expect(onEscape).toHaveBeenCalledOnce()
  })

  it('blurs on Escape when nobody else wants it', () => {
    render(<CategorySearch />)
    input().focus()
    fireEvent.keyDown(input(), { key: 'Escape' })
    expect(input()).not.toHaveFocus()
  })
})
