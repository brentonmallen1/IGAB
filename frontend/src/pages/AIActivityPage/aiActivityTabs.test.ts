import { describe, expect, it } from 'vitest'
import { AI_ACTIVITY_TABS, resolveTab } from './aiActivityTabs'

describe('resolveTab', () => {
  it('keeps a known tab', () => {
    expect(resolveTab('calls')).toBe('calls')
    expect(resolveTab('chats')).toBe('chats')
  })

  it('falls back for a tab that no longer exists', () => {
    // The trap ReportsPage hit when a tab was renamed: a stored id with no
    // panel behind it renders blank with no way back.
    expect(resolveTab('jobs')).toBe('scans')
  })

  it('falls back for nothing stored', () => {
    expect(resolveTab(null)).toBe('scans')
    expect(resolveTab(undefined)).toBe('scans')
    expect(resolveTab('')).toBe('scans')
  })
})

describe('the tab list', () => {
  it('names three tabs', () => {
    expect(AI_ACTIVITY_TABS.map((t) => t.id)).toEqual(['scans', 'chats', 'calls'])
  })

  it('gives every tab a sentence explaining itself', () => {
    // The second user of this app is not technical; a bare label is not enough.
    for (const tab of AI_ACTIVITY_TABS) {
      expect(tab.blurb.length).toBeGreaterThan(30)
      expect(tab.blurb.endsWith('.')).toBe(true)
    }
  })

  it('avoids implementation words in the labels', () => {
    const labels = AI_ACTIVITY_TABS.map((t) => t.label.toLowerCase())
    expect(labels).not.toContain('jobs')
    expect(labels).not.toContain('queue')
  })
})
