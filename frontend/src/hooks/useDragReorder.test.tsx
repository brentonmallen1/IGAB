import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useDragReorder } from './useDragReorder'

describe('useDragReorder', () => {
  it('a drag that drops elsewhere moves once and clears itself', () => {
    const onMove = vi.fn()
    const { result } = renderHook(() => useDragReorder(3, onMove))

    act(() => result.current.start(0))
    act(() => result.current.over(2))
    expect(result.current.dragIndex).toBe(0)
    expect(result.current.overIndex).toBe(2)

    act(() => result.current.drop(2))
    expect(onMove).toHaveBeenCalledTimes(1)
    expect(onMove).toHaveBeenCalledWith(0, 2)
    expect(result.current.dragIndex).toBeNull()
    expect(result.current.overIndex).toBeNull()
  })

  it('dropping on itself moves nothing', () => {
    const onMove = vi.fn()
    const { result } = renderHook(() => useDragReorder(3, onMove))
    act(() => result.current.start(1))
    act(() => result.current.drop(1))
    expect(onMove).not.toHaveBeenCalled()
  })

  it('ending without a drop clears the drag', () => {
    const onMove = vi.fn()
    const { result } = renderHook(() => useDragReorder(3, onMove))
    act(() => result.current.start(1))
    act(() => result.current.over(2))
    act(() => result.current.end())
    expect(result.current.dragIndex).toBeNull()
    expect(result.current.overIndex).toBeNull()
    expect(onMove).not.toHaveBeenCalled()
  })

  it('moveBy clamps at both ends', () => {
    const onMove = vi.fn()
    const { result } = renderHook(() => useDragReorder(3, onMove))
    act(() => result.current.moveBy(0, -1))
    act(() => result.current.moveBy(2, 1))
    expect(onMove).not.toHaveBeenCalled()
    act(() => result.current.moveBy(1, 1))
    expect(onMove).toHaveBeenCalledWith(1, 2)
  })

  it('is stable across renders while nothing is being dragged', () => {
    const onMove = vi.fn()
    const { result, rerender } = renderHook(() => useDragReorder(3, onMove))
    const first = result.current
    rerender()
    expect(result.current).toBe(first)
  })
})
