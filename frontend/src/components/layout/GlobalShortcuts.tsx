import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAppStore } from '../../stores/appStore'
import { useShortcut } from '../../hooks/useShortcut'
import { SHORTCUTS } from '../../keyboard/shortcuts'
import { ShortcutHelp } from '../common/ShortcutHelp/ShortcutHelp'
import { addMonths, currentMonthStart } from '../../utils/dates'

/** App-wide shortcut registrations + the '?' help overlay. */
export function GlobalShortcuts() {
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)
  const [helpOpen, setHelpOpen] = useState(false)
  // Month nav only exists on the budget page; firing these elsewhere would
  // change the month invisibly.
  const onBudgetPage = useLocation().pathname === '/budget'

  useShortcut(SHORTCUTS.help.combo, () => setHelpOpen((o) => !o))
  useShortcut('escape', () => setHelpOpen(false), { enabled: helpOpen, allowInInputs: true })
  useShortcut(SHORTCUTS.monthPrev.combo, () => setSelectedMonth(addMonths(selectedMonth, -1)), {
    enabled: onBudgetPage,
  })
  useShortcut(SHORTCUTS.monthNext.combo, () => setSelectedMonth(addMonths(selectedMonth, 1)), {
    enabled: onBudgetPage,
  })
  useShortcut(SHORTCUTS.monthToday.combo, () => setSelectedMonth(currentMonthStart()), {
    enabled: onBudgetPage,
  })
  useShortcut(SHORTCUTS.privacy.combo, togglePrivacyMode)

  if (!helpOpen) return null
  return <ShortcutHelp onClose={() => setHelpOpen(false)} />
}
