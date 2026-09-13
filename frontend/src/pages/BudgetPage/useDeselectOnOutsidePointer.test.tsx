import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useDeselectOnOutsidePointer } from './useDeselectOnOutsidePointer'
import { KEEPS_SELECTION_ATTR } from '../../utils/keepsSelection'

function press(el: Element) {
  el.dispatchEvent(new Event('pointerdown', { bubbles: true }))
}

afterEach(() => {
  document.getElementById('root')?.remove()
})

function mountRoot() {
  const root = document.createElement('div')
  root.id = 'root'
  root.innerHTML = `<div id="outside"></div><div ${KEEPS_SELECTION_ATTR}=""><span id="row"></span></div>`
  document.body.appendChild(root)
  return { outside: root.querySelector('#outside')!, row: root.querySelector('#row')! }
}

describe('useDeselectOnOutsidePointer', () => {
  it('clears on a press elsewhere in the page, not on a row', () => {
    const { outside, row } = mountRoot()
    const clear = vi.fn()
    renderHook(() => useDeselectOnOutsidePointer(true, clear))
    press(row)
    expect(clear).not.toHaveBeenCalled()
    press(outside)
    expect(clear).toHaveBeenCalledTimes(1)
  })

  it('does not listen while nothing is selected', () => {
    const { outside } = mountRoot()
    const clear = vi.fn()
    renderHook(() => useDeselectOnOutsidePointer(false, clear))
    press(outside)
    expect(clear).not.toHaveBeenCalled()
  })
})
