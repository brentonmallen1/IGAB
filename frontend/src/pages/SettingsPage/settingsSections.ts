/**
 * Which settings sections exist, which page each lives on, and which of them
 * a given person can see.
 *
 * One list, three readers: both settings pages render their nav from it, and
 * the command palette builds a row per section from it. Copying the ids into
 * `commands.ts` is exactly the duplicate this repo's rule is about — the
 * palette would keep offering a section that had been renamed, or miss one
 * that was added, and neither would fail a test.
 *
 * The gates travel with the list for the same reason. A palette that offered
 * "System: Users" to a non-admin, or "Settings: Tags" with no budget open,
 * would be sending someone to a section that is not rendered.
 *
 * Two pages, one rule for which is which: **Settings** is about you and the
 * budget you have open — appearance, formats, accounts, this budget's own
 * backups. **System** is the installation — every budget, every user: server
 * backups and restore, updates, bank connections, the AI model, who can log
 * in. The split exists because Settings sits inside the budget shell, which
 * redirects to the budget picker when there is nothing to show; so the one
 * screen you reach when the database has no usable data was the one screen
 * with no way to put data back. System is reachable with no budget at all.
 */

export type SettingsPageId = 'settings' | 'system'

export const SETTINGS_PAGES: Record<SettingsPageId, { path: string; label: string }> = {
  settings: { path: '/settings', label: 'Settings' },
  system: { path: '/system', label: 'System' },
}

export type SettingsSectionId =
  | 'appearance'
  | 'budget'
  | 'tags'
  | 'guide'
  | 'mobile'
  | 'accounts'
  | 'integrity'
  | 'budget-backups'
  | 'account'
  | 'data'
  | 'updates'
  | 'simplefin'
  | 'ai'
  | 'users'

export interface SettingsSectionDef {
  id: SettingsSectionId
  label: string
  page: SettingsPageId
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

/** In the order the pages lay them out — the palette inherits that order. */
export const SETTINGS_SECTIONS: SettingsSectionDef[] = [
  { id: 'appearance', label: 'Appearance', page: 'settings' },
  { id: 'budget', label: 'Budget', page: 'settings' },
  { id: 'tags', label: 'Tags', page: 'settings', needsBudget: true },
  { id: 'guide', label: 'Guide', page: 'settings', needsBudget: true },
  { id: 'mobile', label: 'Mobile', page: 'settings' },
  { id: 'accounts', label: 'Accounts', page: 'settings', needsBudget: true },
  {
    id: 'integrity',
    label: 'Data Integrity',
    page: 'settings',
    needsBudget: true,
    keywords: 'health verify audit check',
  },
  {
    id: 'budget-backups',
    label: 'Budget Backups',
    page: 'settings',
    needsBudget: true,
    keywords: 'snapshot export duplicate restore download',
  },
  { id: 'account', label: 'Account', page: 'settings', keywords: 'password sign out' },
  // "Backups" sat directly under "Budget Backups" in the nav, and the nav is
  // the only thing that distinguishes them. This one is the whole install.
  {
    id: 'data',
    label: 'Server Backups',
    page: 'system',
    adminOnly: true,
    keywords: 'export restore dump download admin installation',
  },
  { id: 'updates', label: 'Updates', page: 'system', keywords: 'version release' },
  { id: 'simplefin', label: 'SimpleFIN', page: 'system', keywords: 'bank sync connection' },
  { id: 'ai', label: 'AI', page: 'system', keywords: 'ollama model receipts' },
  { id: 'users', label: 'Users', page: 'system', adminOnly: true, keywords: 'household admin' },
]

export interface VisibleSection {
  id: SettingsSectionId
  label: string
  page: SettingsPageId
  warn?: string
  keywords?: string
}

export interface SectionVisibility {
  budgetId: string | null
  isAdmin: boolean
  /** Only this page's sections; both pages when omitted (the palette). */
  page?: SettingsPageId
  /** Shown against SimpleFIN when the server has no encryption key: the
   *  section is reachable, but there is something to fix inside it. */
  sfWarn?: string
}

export function visibleSettingsSections({
  budgetId,
  isAdmin,
  page,
  sfWarn,
}: SectionVisibility): VisibleSection[] {
  return SETTINGS_SECTIONS.filter(
    (section) =>
      (!page || section.page === page) &&
      (!section.needsBudget || !!budgetId) &&
      (!section.adminOnly || isAdmin)
  ).map((section) => ({
    id: section.id,
    label: section.label,
    page: section.page,
    keywords: section.keywords,
    ...(section.id === 'simplefin' && sfWarn ? { warn: sfWarn } : {}),
  }))
}

/** The one place a section's address is spelled: `/system#data`. */
export function sectionHref(section: Pick<VisibleSection, 'id' | 'page'>): string {
  return `${SETTINGS_PAGES[section.page].path}#${section.id}`
}
