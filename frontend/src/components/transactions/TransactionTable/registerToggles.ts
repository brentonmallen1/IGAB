import { ListTree, Sigma, type LucideIcon } from 'lucide-react'

/** One standing choice about how the register draws its rows. */
export interface RegisterToggle {
  id: 'split-lines' | 'running-balance'
  /** What is shown, for "Show …" / "Hide …". */
  noun: string
  /** What switching it on does, where there is room to say (Settings). */
  description: string
  icon: LucideIcon
  show: boolean
  onChange: (show: boolean) => void
}

interface ToggleState {
  showSplitLines: boolean
  setShowSplitLines: (show: boolean) => void
  showRunningBalance: boolean
  setShowRunningBalance: (show: boolean) => void
}

/**
 * The register's view toggles, once, for every place that draws them: the
 * desktop toolbar beside the search box and the phone account page's Tools
 * sheet. Each used to hand-write its own split-lines button, so a second
 * toggle would have been two more copies to keep in step.
 *
 * The running balance is one account's — across accounts it is not a balance
 * of anything — so the all-accounts register does not offer it.
 */
export function registerToggles(state: ToggleState, allAccounts: boolean): RegisterToggle[] {
  const toggles: RegisterToggle[] = [
    {
      id: 'split-lines',
      noun: 'split lines',
      description: 'Draw each split’s lines under it, with their categories and memos.',
      icon: ListTree,
      show: state.showSplitLines,
      onChange: state.setShowSplitLines,
    },
  ]
  if (!allAccounts) {
    toggles.push({
      id: 'running-balance',
      noun: 'running balance',
      description:
        'Show the account’s balance after each row, with the register in date order. Rows waiting in Pending or Needs Review sit above the list, so the figures step over them, as they would on a filtered statement. Not on the all-accounts register: a total across accounts is not a balance.',
      icon: Sigma,
      show: state.showRunningBalance,
      onChange: state.setShowRunningBalance,
    })
  }
  return toggles
}
