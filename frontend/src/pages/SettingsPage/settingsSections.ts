/**
 * Which settings sections exist, which page each lives on, which group it
 * sits under, what it is for, and which of them a given person can see.
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
 *
 * A section is shown one at a time, at its own address (`/settings/budget`),
 * so the description here is the sentence at the top of that view: what the
 * section is for, said once, where a person deciding whether they are in the
 * right place will read it.
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
  | 'api-keys'
  | 'data'
  | 'updates'
  | 'simplefin'
  | 'sync-logs'
  | 'ai'
  | 'users'

/**
 * The nav's headings. Ten sections in one flat list told nobody which were
 * about them, which about the open budget, and which about its data — so the
 * list says. A group belongs to one page; the test pins that a section's
 * group is on the section's page.
 */
export type SettingsGroupId = 'you' | 'this-budget' | 'data' | 'installation' | 'connections'

export const SETTINGS_GROUPS: Record<SettingsGroupId, { label: string; page: SettingsPageId }> = {
  you: { label: 'Personal', page: 'settings' },
  'this-budget': { label: 'This budget', page: 'settings' },
  data: { label: 'Data & access', page: 'settings' },
  installation: { label: 'Installation', page: 'system' },
  connections: { label: 'Connections', page: 'system' },
}

export interface SettingsSectionDef {
  id: SettingsSectionId
  label: string
  page: SettingsPageId
  group: SettingsGroupId
  /** One sentence under the title: what this section is for. */
  description: string
  /** Sections about the open budget: nothing to show without one. */
  needsBudget?: boolean
  /** Whole-installation settings. Every endpoint behind these is admin-gated,
   *  so showing them to anyone else only collects 403s. */
  adminOnly?: boolean
  /** Extra search terms for the command palette and the nav's own search.
   *  They live here rather than in commands.ts so a section carries its own
   *  vocabulary — these are the words the two hand-written "Run integrity
   *  check" / "Backups" rows used to carry before they became duplicates of
   *  a generated row. */
  keywords?: string
}

/** In the order the pages lay them out — grouped, and the palette inherits
 *  that order. */
export const SETTINGS_SECTIONS: SettingsSectionDef[] = [
  // ── Personal ──
  {
    id: 'appearance',
    label: 'Appearance',
    page: 'settings',
    group: 'you',
    description: 'How the app looks on this device. Nothing here changes the budget.',
    keywords: 'theme palette dark light font text size',
  },
  {
    id: 'mobile',
    label: 'Mobile',
    page: 'settings',
    group: 'you',
    description: 'Settings that live on this phone and are not sent to the server.',
    keywords: 'location phone viewport',
  },
  {
    id: 'account',
    label: 'Account',
    page: 'settings',
    group: 'you',
    description: 'Who you are signed in as, your password, and signing out.',
    keywords: 'password sign out email',
  },
  // ── This budget ──
  {
    id: 'budget',
    label: 'Budget',
    page: 'settings',
    group: 'this-budget',
    description:
      'The budget you have open: its name, when a month’s money is expected, and how its numbers are written everywhere they appear.',
    keywords: 'name currency number date time format funding day',
  },
  {
    id: 'accounts',
    label: 'Accounts',
    page: 'settings',
    group: 'this-budget',
    needsBudget: true,
    description: 'Every account in this budget — add one, edit one, close or reopen it.',
    keywords: 'checking savings card loan add close',
  },
  {
    id: 'tags',
    label: 'Tags',
    page: 'settings',
    group: 'this-budget',
    needsBudget: true,
    description: 'The tags this budget uses to mark transactions and envelopes.',
    keywords: 'essential label colour color',
  },
  {
    id: 'guide',
    label: 'Guide',
    page: 'settings',
    group: 'this-budget',
    needsBudget: true,
    description:
      'What the Guide is allowed to work out from your budget, and whether it keeps a wishlist.',
    keywords: 'roadmap checkup health wishlist personalise',
  },
  // ── Data & access ──
  {
    id: 'integrity',
    label: 'Data Integrity',
    page: 'settings',
    group: 'data',
    needsBudget: true,
    description: 'Check this budget’s figures agree with themselves, and fix what does not.',
    keywords: 'health verify audit check',
  },
  {
    id: 'budget-backups',
    label: 'Budget Backups',
    page: 'settings',
    group: 'data',
    needsBudget: true,
    description:
      'A file holding this one budget, which can be restored here or into another install.',
    keywords: 'snapshot export duplicate restore download',
  },
  {
    id: 'api-keys',
    label: 'MCP',
    page: 'settings',
    group: 'data',
    description:
      'A read-only endpoint so an assistant can answer questions about a budget. Keys read only the budgets you name.',
    keywords: 'mcp api key token claude assistant ai read-only integration connect endpoint',
  },
  // ── System · Installation ──
  // "Backups" sat directly under "Budget Backups" in the nav, and the nav is
  // the only thing that distinguishes them. This one is the whole install.
  {
    id: 'data',
    label: 'Server Backups',
    page: 'system',
    group: 'installation',
    adminOnly: true,
    description:
      'A dump of the whole installation — every budget and every user — and the way to restore one.',
    keywords: 'export restore dump download admin installation',
  },
  {
    id: 'updates',
    label: 'Updates',
    page: 'system',
    group: 'installation',
    description: 'The version this install is running, and whether a newer one exists.',
    keywords: 'version release',
  },
  {
    id: 'users',
    label: 'Users',
    page: 'system',
    group: 'installation',
    adminOnly: true,
    description: 'Who can sign in to this install, and which of them are admins.',
    keywords: 'household admin',
  },
  // ── System · Connections ──
  {
    id: 'simplefin',
    label: 'SimpleFIN',
    page: 'system',
    group: 'connections',
    description: 'The bank connection every budget syncs through, and when it runs.',
    keywords: 'bank sync connection',
  },
  {
    id: 'sync-logs',
    label: 'Sync Logs',
    page: 'system',
    group: 'connections',
    adminOnly: true,
    description: 'What each bank sync did, account by account, and what it refused.',
    keywords: 'sync history bank simplefin log diagnostics skipped imported',
  },
  {
    id: 'ai',
    label: 'AI',
    page: 'system',
    group: 'connections',
    description:
      'The Ollama server behind receipt scanning, suggestions, and the assistant — and which models do which job.',
    keywords: 'ollama model receipts assistant',
  },
]

export interface VisibleSection {
  id: SettingsSectionId
  label: string
  page: SettingsPageId
  group: SettingsGroupId
  description: string
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
    group: section.group,
    description: section.description,
    keywords: section.keywords,
    ...(section.id === 'simplefin' && sfWarn ? { warn: sfWarn } : {}),
  }))
}

/** The one place a section's address is spelled: `/system/data`. */
export function sectionHref(section: Pick<VisibleSection, 'id' | 'page'>): string {
  return `${SETTINGS_PAGES[section.page].path}/${section.id}`
}

/**
 * The section a path names, or null: `/settings/budget` → `budget`. Read
 * from the pathname rather than a route param so it works wherever the
 * page is mounted — tests render it without a `<Routes>`.
 */
export function sectionIdFromPath(page: SettingsPageId, pathname: string): string | null {
  const base = `${SETTINGS_PAGES[page].path}/`
  if (!pathname.startsWith(base)) return null
  const rest = pathname.slice(base.length).split('/')[0]
  return rest || null
}

export interface SectionGroup {
  id: SettingsGroupId
  label: string
  sections: VisibleSection[]
}

/** The nav's shape: groups in list order, each with its visible sections,
 *  empty groups left out — a heading over nothing is a question. */
export function groupedSections(sections: VisibleSection[]): SectionGroup[] {
  const groups: SectionGroup[] = []
  for (const section of sections) {
    let group = groups.find((g) => g.id === section.group)
    if (!group) {
      group = { id: section.group, label: SETTINGS_GROUPS[section.group].label, sections: [] }
      groups.push(group)
    }
    group.sections.push(section)
  }
  return groups
}

/**
 * The nav's search. Matches the label, the description and the keywords —
 * the same vocabulary the palette searches, so a word that finds a section
 * there finds it here. An empty query is no filter.
 */
export function filterSections(sections: VisibleSection[], query: string): VisibleSection[] {
  const q = query.trim().toLowerCase()
  if (!q) return sections
  return sections.filter((s) =>
    `${s.label} ${s.description} ${s.keywords ?? ''}`.toLowerCase().includes(q)
  )
}

/** The sections either side of one, in nav order, for the foot of a view. */
export function neighbours(
  sections: VisibleSection[],
  id: string
): { prev: VisibleSection | null; next: VisibleSection | null } {
  const i = sections.findIndex((s) => s.id === id)
  if (i < 0) return { prev: null, next: null }
  return { prev: sections[i - 1] ?? null, next: sections[i + 1] ?? null }
}
