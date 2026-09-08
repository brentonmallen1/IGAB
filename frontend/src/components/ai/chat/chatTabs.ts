/**
 * The panel's open conversations, as tabs.
 *
 * Pure: every rule about which tab is open, which one a click lands on and
 * what happens when the last one closes is a one-line test here, and the
 * store only supplies keys. A tab is keyed by the client, not the
 * conversation id, because a new chat has no id until the server answers
 * its first message.
 */

export interface ChatTab {
  /** Client-side identity, stable for the life of the tab. */
  key: string
  /** The server's conversation, once there is one. */
  conversationId: string | null
  /** What the tab says before the conversation list can name it. */
  label: string | null
}

export interface ChatTabsState {
  tabs: ChatTab[]
  activeKey: string | null
}

export function blankTab(key: string): ChatTab {
  return { key, conversationId: null, label: null }
}

function isBlank(tab: ChatTab): boolean {
  return tab.conversationId === null && tab.label === null
}

/**
 * Start a new chat. An untouched blank tab is reused rather than joined by a
 * second one — two empty tabs is not two conversations.
 */
export function newTab(state: ChatTabsState, key: string): ChatTabsState {
  const blank = state.tabs.find(isBlank)
  if (blank) return { ...state, activeKey: blank.key }
  return { tabs: [...state.tabs, blankTab(key)], activeKey: key }
}

/**
 * Bring a conversation into the panel: its own tab if it already has one,
 * the active tab if that one is still blank, a new tab otherwise.
 */
export function openConversation(
  state: ChatTabsState,
  conversationId: string,
  key: string
): ChatTabsState {
  const existing = state.tabs.find((t) => t.conversationId === conversationId)
  if (existing) return { ...state, activeKey: existing.key }
  const active = state.tabs.find((t) => t.key === state.activeKey)
  if (active && isBlank(active)) {
    return {
      ...state,
      tabs: state.tabs.map((t) => (t.key === active.key ? { ...t, conversationId } : t)),
    }
  }
  const tab: ChatTab = { key, conversationId, label: null }
  return { tabs: [...state.tabs, tab], activeKey: key }
}

/**
 * Close one tab. Closing the active one lands on its right-hand neighbour,
 * or the left when it was last; closing the only tab leaves a blank one
 * under `freshKey`, because a panel with no tab has nowhere to type.
 */
export function closeTab(state: ChatTabsState, key: string, freshKey: string): ChatTabsState {
  const index = state.tabs.findIndex((t) => t.key === key)
  if (index === -1) return state
  const tabs = state.tabs.filter((t) => t.key !== key)
  if (tabs.length === 0) return { tabs: [blankTab(freshKey)], activeKey: freshKey }
  if (state.activeKey !== key) return { ...state, tabs }
  const next = tabs[Math.min(index, tabs.length - 1)]
  return { tabs, activeKey: next.key }
}

/** Close every tab showing a conversation that no longer exists. */
export function closeConversation(
  state: ChatTabsState,
  conversationId: string,
  freshKey: string
): ChatTabsState {
  return state.tabs
    .filter((t) => t.conversationId === conversationId)
    .reduce((s, t) => closeTab(s, t.key, freshKey), state)
}

/** The server named the conversation a tab's first message started. */
export function assignConversation(
  state: ChatTabsState,
  key: string,
  conversationId: string
): ChatTabsState {
  return {
    ...state,
    tabs: state.tabs.map((t) => (t.key === key ? { ...t, conversationId } : t)),
  }
}

/** Give a tab a name of its own until the conversation list supplies one. */
export function labelTab(state: ChatTabsState, key: string, label: string): ChatTabsState {
  return { ...state, tabs: state.tabs.map((t) => (t.key === key ? { ...t, label } : t)) }
}
