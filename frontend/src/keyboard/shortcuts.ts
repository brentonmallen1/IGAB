/**
 * Single source of truth for keyboard shortcuts: registration (via
 * useShortcut combos), context-menu hints, and the '?' help overlay all read
 * from here so displayed hints can never drift from actual bindings.
 */

export const IS_MAC = /Mac|iPhone|iPad/.test(navigator.userAgent)

export interface ShortcutDef {
  /** Combo for useShortcut ("mod+k", "shift+d", "?", "[") */
  combo: string
  label: string
  group: 'Global' | 'Budget' | 'Transactions'
}

export const SHORTCUTS = {
  palette: { combo: 'mod+k', label: 'Open command palette', group: 'Global' },
  help: { combo: '?', label: 'Show keyboard shortcuts', group: 'Global' },
  monthPrev: { combo: '[', label: 'Previous month', group: 'Global' },
  monthNext: { combo: ']', label: 'Next month', group: 'Global' },
  monthToday: { combo: 't', label: 'Jump to current month', group: 'Global' },
  undo: { combo: 'mod+z', label: 'Undo last edit', group: 'Transactions' },
  duplicate: { combo: 'shift+d', label: 'Duplicate selected', group: 'Transactions' },
  makeRepeating: {
    combo: 'shift+t',
    label: 'Make repeating (single selection)',
    group: 'Transactions',
  },
  deleteSelected: { combo: 'delete', label: 'Delete selected', group: 'Transactions' },
} as const satisfies Record<string, ShortcutDef>

/** "mod+k" → "⌘K" (mac) / "Ctrl+K"; "shift+d" → "Shift+D"; "[" → "[" */
export function formatCombo(combo: string): string {
  return combo
    .split('+')
    .map((part) => {
      switch (part) {
        case 'mod':
          return IS_MAC ? '⌘' : 'Ctrl+'
        case 'shift':
          return 'Shift+'
        case 'alt':
          return IS_MAC ? '⌥' : 'Alt+'
        case 'delete':
          return IS_MAC ? '⌫' : 'Del'
        default:
          return part.length === 1 ? part.toUpperCase() : part
      }
    })
    .join('')
    .replace(/\+$/, '')
}
