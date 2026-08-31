/**
 * Which settings sections exist, and which of them a given person can see.
 *
 * One list, two readers: the page renders its nav from it, and the command
 * palette builds a row per section from it. Copying the ids into `commands.ts`
 * is exactly the duplicate this repo's rule is about — the palette would keep
 * offering a section that had been renamed, or miss one that was added, and
 * neither would fail a test.
 *
 * The gates travel with the list for the same reason. A palette that offered
 * "Settings: Users" to a non-admin, or "Settings: Tags" with no budget open,
 * would be sending someone to a section that is not rendered.
 */

export type SettingsSectionId =
  | 'appearance'
  | 'budget'
  | 'tags'
  | 'guide'
  | 'mobile'
  | 'accounts'
  | 'integrity'
  | 'budget-backups'
  | 'data'
  | 'updates'
  | 'simplefin'
  | 'ai'
  | 'account'
  | 'users'

export interface SettingsSectionDef {
  id: SettingsSectionId
  label: string
  /** Sections about the open budget: nothing to show without one. */
  needsBudget?: boolean
  /** Whole-installation settings. Every endpoint behind these is admin-gated,
   *  so showing them to anyone else only collects 403s. */
  adminOnly?: boolean
  /** Extra search terms for the command palette. They live here rather than
   *  in commands.ts so a section carries its own vocabulary — these are the
   *  words the two hand-written "Run integrity check" / "Backups" rows used
   *  to carry before they became duplicates of a generated row. */
  keywords?: string
}

/** In the order the page lays them out — the palette inherits that order. */
export const SETTINGS_SECTIONS: SettingsSectionDef[] = [
  { id: 'appearance', label: 'Appearance' },
  { id: 'budget', label: 'Budget' },
  { id: 'tags', label: 'Tags', needsBudget: true },
  { id: 'guide', label: 'Guide', needsBudget: true },
  { id: 'mobile', label: 'Mobile' },
  { id: 'accounts', label: 'Accounts', needsBudget: true },
  {
    id: 'integrity',
    label: 'Data Integrity',
    needsBudget: true,
    keywords: 'health verify audit check',
  },
  {
    id: 'budget-backups',
    label: 'Budget Backups',
    needsBudget: true,
    keywords: 'snapshot export duplicate restore download',
  },
  { id: 'data', label: 'Backups', adminOnly: true, keywords: 'export restore dump download' },
  { id: 'updates', label: 'Updates' },
  { id: 'simplefin', label: 'SimpleFIN' },
  { id: 'ai', label: 'AI' },
  { id: 'account', label: 'Account' },
  { id: 'users', label: 'Users', adminOnly: true },
]

export interface VisibleSection {
  id: SettingsSectionId
  label: string
  warn?: string
  keywords?: string
}

export interface SectionVisibility {
  budgetId: string | null
  isAdmin: boolean
  /** Shown against SimpleFIN when the server has no encryption key: the
   *  section is reachable, but there is something to fix inside it. */
  sfWarn?: string
}

export function visibleSettingsSections({
  budgetId,
  isAdmin,
  sfWarn,
}: SectionVisibility): VisibleSection[] {
  return SETTINGS_SECTIONS.filter(
    (section) => (!section.needsBudget || !!budgetId) && (!section.adminOnly || isAdmin)
  ).map((section) => ({
    id: section.id,
    label: section.label,
    keywords: section.keywords,
    ...(section.id === 'simplefin' && sfWarn ? { warn: sfWarn } : {}),
  }))
}
