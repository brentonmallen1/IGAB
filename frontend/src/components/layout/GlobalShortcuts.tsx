import { useState } from 'react'
import { useAppStore } from '../../stores/appStore'
import { useShortcut } from '../../hooks/useShortcut'
import { SHORTCUTS } from '../../keyboard/shortcuts'
import { ShortcutHelp } from '../common/ShortcutHelp/ShortcutHelp'
import { addMonths, currentMonthStart } from '../../utils/dates'

/** App-wide shortcut registrations + the '?' help overlay. */
export function GlobalShortcuts() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const [helpOpen, setHelpOpen] = useState(false)

  useShortcut(SHORTCUTS.help.combo, () => setHelpOpen((o) => !o))
  useShortcut('escape', () => setHelpOpen(false), { enabled: helpOpen, allowInInputs: true })
  useShortcut(SHORTCUTS.monthPrev.combo, () => setSelectedMonth(addMonths(selectedMonth, -1)))
  useShortcut(SHORTCUTS.monthNext.combo, () => setSelectedMonth(addMonths(selectedMonth, 1)))
  useShortcut(SHORTCUTS.monthToday.combo, () => setSelectedMonth(currentMonthStart()))

  if (!helpOpen) return null
  return <ShortcutHelp onClose={() => setHelpOpen(false)} />
}
