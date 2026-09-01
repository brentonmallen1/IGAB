/**
 * The modal slot.
 *
 * This was eight independent booleans, each with its own editing-id and its
 * own open/close pair, and nothing stopped two being true at once — raising
 * the filter dialog while the view dialog stood rendered both, stacked. Being
 * able to represent that at all was the bug, so what is pinned here is that
 * the state cannot express it any more.
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { PERSIST_KEYS } from './persistKeys'
import { useUIStore } from './uiStore'

beforeEach(() => {
  useUIStore.getState().closeModal()
})

describe('uiStore modals', () => {
  it('starts with nothing open', () => {
    expect(useUIStore.getState().activeModal).toBeNull()
  })

  it('carries the row being edited', () => {
    useUIStore.getState().openModal('filter', 'f1')

    expect(useUIStore.getState().activeModal).toEqual({ kind: 'filter', editingId: 'f1' })
  })

  it('treats a missing id as "new"', () => {
    useUIStore.getState().openModal('view')

    expect(useUIStore.getState().activeModal).toEqual({ kind: 'view', editingId: null })
  })

  it('cannot hold two dialogs at once', () => {
    useUIStore.getState().openModal('view', 'v1')
    useUIStore.getState().openModal('filter', 'f1')

    expect(useUIStore.getState().activeModal).toEqual({ kind: 'filter', editingId: 'f1' })
  })

  it('does not carry an id across a change of dialog', () => {
    // The old shape kept a separate id per modal, so a stale one could outlive
    // its dialog. One slot means one id, replaced whole.
    useUIStore.getState().openModal('account', 'acct-1')
    useUIStore.getState().openModal('add-account')

    expect(useUIStore.getState().activeModal?.editingId).toBeNull()
  })

  it('closes to nothing', () => {
    useUIStore.getState().openModal('manage-views')
    useUIStore.getState().closeModal()

    expect(useUIStore.getState().activeModal).toBeNull()
  })

  it('is not restored from storage — a reload should not reopen a dialog', () => {
    // Asserted against a blob that is definitely there: an absent key would
    // make "activeModal is undefined" true for the wrong reason.
    useUIStore.getState().setActiveView('v1')
    useUIStore.getState().openModal('transaction', 't1')

    const persisted = JSON.parse(localStorage.getItem(PERSIST_KEYS.ui) ?? '{}')

    expect(persisted.state?.activeViewId).toBe('v1')
    expect(persisted.state?.activeModal).toBeUndefined()
  })
})

describe('budget group folds', () => {
  beforeEach(() => {
    useUIStore.setState({ collapsedGroups: new Set() })
  })

  it('collapse-all and expand-all touch only the groups on screen', () => {
    // g3 is hidden by a filter and stays exactly as the user left it: the
    // old collapseAll REPLACED the set (expanding g3), and the old
    // expandAll cleared it (also expanding g3).
    useUIStore.getState().toggleGroupExpanded('g3')

    useUIStore.getState().collapseAll(['g1', 'g2'])
    expect([...useUIStore.getState().collapsedGroups].sort()).toEqual(['g1', 'g2', 'g3'])

    useUIStore.getState().expandAll(['g1', 'g2'])
    expect([...useUIStore.getState().collapsedGroups]).toEqual(['g3'])
  })

  it('persists the folds as an array and rehydrates them as a Set', () => {
    // A Set JSON-stringifies to {} and rehydrates as a plain object whose
    // .has is undefined — the same trap collapsedSidebarGroups documents.
    useUIStore.getState().collapseAll(['g1'])

    const persisted = JSON.parse(localStorage.getItem(PERSIST_KEYS.ui) ?? '{}')
    expect(persisted.state?.collapsedGroups).toEqual(['g1'])
  })
})
