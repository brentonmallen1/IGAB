/**
 * The three views of what the AI has done.
 *
 * Named for the household rather than the implementation. "Jobs" and "Calls"
 * mean nothing to the second, less technical person this app is built for, and
 * they overlap invisibly — every scan produces calls. "Scans" is the work you
 * asked for, "Chats" is what you asked about, "Model calls" is the machinery
 * underneath, and each tab says so in a sentence.
 */
export interface AIActivityTabDef {
  id: AIActivityTab
  label: string
  /** One line under the heading: what this tab is, in plain terms. */
  blurb: string
}

export type AIActivityTab = 'scans' | 'chats' | 'calls'

export const AI_ACTIVITY_TABS: AIActivityTabDef[] = [
  {
    id: 'scans',
    label: 'Scans',
    blurb:
      'Every receipt and typed entry the AI turned into a transaction, and which of them still need your approval.',
  },
  {
    id: 'chats',
    label: 'Chats',
    blurb: 'Questions you asked the assistant, and what it answered.',
  },
  {
    id: 'calls',
    label: 'Model calls',
    blurb:
      'Every request this app made to a model — what was sent, what came back, and what it looked up on the way.',
  },
]

const IDS = new Set<string>(AI_ACTIVITY_TABS.map((t) => t.id))

/**
 * A stored tab id, or the default.
 *
 * Guards the trap ReportsPage hit when a tab was renamed: a persisted id that
 * no longer exists otherwise renders a blank panel with no way back.
 */
export function resolveTab(stored: string | null | undefined): AIActivityTab {
  return stored && IDS.has(stored) ? (stored as AIActivityTab) : 'scans'
}
