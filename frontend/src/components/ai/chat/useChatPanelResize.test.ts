import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatPanelResize } from './useChatPanelResize'
import { useUIStore } from '../../../stores/uiStore'
import { CHAT_PANEL_MAX_WIDTH, CHAT_PANEL_MIN_WIDTH } from './chatPanelWidth'

function pointer(clientX: number) {
  const target = {
    setPointerCapture: vi.fn(),
    releasePointerCapture: vi.fn(),
    hasPointerCapture: vi.fn(() => true),
  }
  return { clientX, pointerId: 1, currentTarget: target } as never
}

function key(k: string) {
  return { key: k, preventDefault: vi.fn() } as never
}

describe('useChatPanelResize', () => {
  beforeEach(() => {
    useUIStore.setState({ chatPanelWidth: 400 })
  })

  it('widens the panel when dragged left', () => {
    // The handle is on the panel's LEFT edge, so a leftward drag grows it —
    // the opposite sign from the sidebar's handle.
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onPointerDown(pointer(1000)))
    act(() => result.current.handleProps.onPointerMove(pointer(940)))
    expect(useUIStore.getState().chatPanelWidth).toBe(460)
  })

  it('narrows the panel when dragged right', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onPointerDown(pointer(1000)))
    act(() => result.current.handleProps.onPointerMove(pointer(1020)))
    expect(useUIStore.getState().chatPanelWidth).toBe(380)
  })

  it('clamps at the ceiling while dragging', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onPointerDown(pointer(1000)))
    act(() => result.current.handleProps.onPointerMove(pointer(0)))
    expect(useUIStore.getState().chatPanelWidth).toBe(CHAT_PANEL_MAX_WIDTH)
  })

  it('ignores a move that never started with a press', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onPointerMove(pointer(500)))
    expect(useUIStore.getState().chatPanelWidth).toBe(400)
  })

  it('stops tracking after the pointer is released', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onPointerDown(pointer(1000)))
    act(() => result.current.handleProps.onPointerUp(pointer(1000)))
    act(() => result.current.handleProps.onPointerMove(pointer(800)))
    expect(useUIStore.getState().chatPanelWidth).toBe(400)
  })

  it('releases capture only when it holds it', () => {
    const { result } = renderHook(() => useChatPanelResize())
    const event = pointer(1000) as unknown as {
      currentTarget: { hasPointerCapture: () => boolean; releasePointerCapture: unknown }
    }
    event.currentTarget.hasPointerCapture = () => false
    act(() => result.current.handleProps.onPointerUp(event as never))
    expect(event.currentTarget.releasePointerCapture).not.toHaveBeenCalled()
  })

  it('resizes with the arrow keys', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onKeyDown(key('ArrowLeft')))
    expect(useUIStore.getState().chatPanelWidth).toBe(416)
    act(() => result.current.handleProps.onKeyDown(key('ArrowRight')))
    expect(useUIStore.getState().chatPanelWidth).toBe(400)
  })

  it('resets to the floor with Home and with a double click', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onKeyDown(key('Home')))
    expect(useUIStore.getState().chatPanelWidth).toBe(CHAT_PANEL_MIN_WIDTH)

    useUIStore.setState({ chatPanelWidth: 500 })
    act(() => result.current.handleProps.onDoubleClick())
    expect(useUIStore.getState().chatPanelWidth).toBe(CHAT_PANEL_MIN_WIDTH)
  })

  it('ignores keys it does not handle', () => {
    const { result } = renderHook(() => useChatPanelResize())
    act(() => result.current.handleProps.onKeyDown(key('a')))
    expect(useUIStore.getState().chatPanelWidth).toBe(400)
  })

  it('announces itself as a separator for screen readers', () => {
    const { result } = renderHook(() => useChatPanelResize())
    expect(result.current.handleProps.role).toBe('separator')
    expect(result.current.handleProps['aria-orientation']).toBe('vertical')
    expect(result.current.handleProps.tabIndex).toBe(0)
  })

  it('reports its width, so an arrow key is audible', () => {
    // A separator with no value announces "separator" and nothing else, and a
    // screen-reader user cannot tell whether the key did anything.
    const { result, rerender } = renderHook(() => useChatPanelResize())
    expect(result.current.handleProps['aria-valuenow']).toBe(400)
    expect(result.current.handleProps['aria-valuemin']).toBe(CHAT_PANEL_MIN_WIDTH)
    expect(result.current.handleProps['aria-valuemax']).toBe(CHAT_PANEL_MAX_WIDTH)

    act(() => result.current.handleProps.onKeyDown(key('ArrowLeft')))
    rerender()
    expect(result.current.handleProps['aria-valuenow']).toBe(416)
  })
})
