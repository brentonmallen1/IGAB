import { describe, it, expect } from 'vitest'
import {
  assignConversation,
  blankTab,
  closeConversation,
  closeTab,
  labelTab,
  newTab,
  openConversation,
  type ChatTabsState,
} from './chatTabs'

const one: ChatTabsState = { tabs: [blankTab('a')], activeKey: 'a' }
const two: ChatTabsState = {
  tabs: [
    { key: 'a', conversationId: 'c1', label: null },
    { key: 'b', conversationId: 'c2', label: null },
  ],
  activeKey: 'a',
}

describe('newTab', () => {
  it('adds and activates a tab beside real conversations', () => {
    const next = newTab(two, 'z')
    expect(next.tabs.map((t) => t.key)).toEqual(['a', 'b', 'z'])
    expect(next.activeKey).toBe('z')
  })

  it('adds a tab even when a blank one is already open', () => {
    // Pressing the button must always show something happening.
    const next = newTab(one, 'z')
    expect(next.tabs).toHaveLength(2)
    expect(next.activeKey).toBe('z')
  })
})

describe('openConversation', () => {
  it('activates the tab a conversation already has', () => {
    expect(openConversation({ ...two, activeKey: 'a' }, 'c2', 'z')).toEqual({
      ...two,
      activeKey: 'b',
    })
  })

  it('fills the active blank tab rather than opening beside it', () => {
    const next = openConversation(one, 'c9', 'z')
    expect(next.tabs).toEqual([{ key: 'a', conversationId: 'c9', label: null }])
    expect(next.activeKey).toBe('a')
  })

  it('opens a new tab when the active one is a real conversation', () => {
    const next = openConversation(two, 'c9', 'z')
    expect(next.tabs).toHaveLength(3)
    expect(next.activeKey).toBe('z')
  })
})

describe('closeTab', () => {
  it('lands on the right-hand neighbour', () => {
    const three = newTab(two, 'z')
    expect(closeTab({ ...three, activeKey: 'a' }, 'a', 'f').activeKey).toBe('b')
  })

  it('lands on the left when the last tab closes', () => {
    expect(closeTab({ ...two, activeKey: 'b' }, 'b', 'f').activeKey).toBe('a')
  })

  it('leaves the selection alone when an inactive tab closes', () => {
    expect(closeTab(two, 'b', 'f').activeKey).toBe('a')
  })

  it('never leaves zero tabs', () => {
    expect(closeTab(one, 'a', 'f')).toEqual({ tabs: [blankTab('f')], activeKey: 'f' })
  })

  it('ignores an unknown key', () => {
    expect(closeTab(two, 'nope', 'f')).toBe(two)
  })
})

describe('closeConversation', () => {
  it('closes every tab on a deleted conversation', () => {
    expect(closeConversation(two, 'c1', 'f').tabs.map((t) => t.key)).toEqual(['b'])
  })
})

describe('assignConversation and labelTab', () => {
  it('names the conversation a tab started', () => {
    const next = assignConversation(one, 'a', 'c5')
    expect(next.tabs[0].conversationId).toBe('c5')
  })

  it('labels only the tab asked for', () => {
    const next = labelTab(two, 'b', 'Payees')
    expect(next.tabs.map((t) => t.label)).toEqual([null, 'Payees'])
  })
})
