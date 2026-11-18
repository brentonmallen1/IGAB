import { describe, expect, it } from 'vitest'
import { KEEPS_SELECTION_ATTR, pressKeepsSelection } from './keepsSelection'

function page() {
  document.body.innerHTML = `
    <div id="root">
      <div class="tba-hero"><button id="hero-btn">Assign</button></div>
      <div class="budget-table">
        <div id="empty-grid"></div>
        <div ${KEEPS_SELECTION_ATTR}="" class="category-row"><input id="row-input" /></div>
      </div>
      <aside ${KEEPS_SELECTION_ATTR}="" class="category-inspector"><button id="inspector-btn"></button></aside>
    </div>
    <div class="modal-portal"><button id="dialog-btn">Save</button></div>`
  const $ = (id: string) => document.getElementById(id)
  return { root: $('root'), $ }
}

describe('pressKeepsSelection', () => {
  it('deselects on a press in the page outside the rows and inspector', () => {
    const { root, $ } = page()
    expect(pressKeepsSelection($('empty-grid'), root)).toBe(false)
    expect(pressKeepsSelection($('hero-btn'), root)).toBe(false)
  })

  it('keeps it on a press inside a row, even on a control within it', () => {
    const { root, $ } = page()
    expect(pressKeepsSelection($('row-input'), root)).toBe(true)
  })

  it('keeps it on a press in the inspector', () => {
    const { root, $ } = page()
    expect(pressKeepsSelection($('inspector-btn'), root)).toBe(true)
  })

  // Dialogs, menus and sheets opened from the selection are portalled to
  // <body>; pressing in one must not cancel what it acts on.
  it('keeps it on a press in anything portalled outside the app root', () => {
    const { root, $ } = page()
    expect(pressKeepsSelection($('dialog-btn'), root)).toBe(true)
  })

  it('keeps it when there is no element target or no root to judge by', () => {
    const { root, $ } = page()
    expect(pressKeepsSelection(null, root)).toBe(true)
    expect(pressKeepsSelection(document, root)).toBe(true)
    expect(pressKeepsSelection($('empty-grid'), null)).toBe(true)
  })
})
