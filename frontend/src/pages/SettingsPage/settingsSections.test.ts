/**
 * The one registry behind two settings pages and the command palette.
 *
 * What it must hold: every section lives on exactly one page, the pages
 * partition the list, a section's address is spelled in one place, a
 * section's group is on the section's page, every section can say what it
 * is for, and the gates (budget open, admin) apply the same way whichever
 * reader asks.
 */
import { describe, expect, it } from 'vitest'
import {
  SETTINGS_GROUPS,
  SETTINGS_PAGES,
  SETTINGS_SECTIONS,
  filterSections,
  groupedSections,
  neighbours,
  sectionHref,
  sectionIdFromPath,
  visibleSettingsSections,
} from './settingsSections'

const admin = { budgetId: 'b1', isAdmin: true }

describe('the two pages partition the sections', () => {
  it('every section is on a page that exists', () => {
    for (const s of SETTINGS_SECTIONS) {
      expect(SETTINGS_PAGES[s.page], `section '${s.id}' names an unknown page`).toBeDefined()
    }
  })

  it('asking per page gives back the whole list, once', () => {
    const settings = visibleSettingsSections({ ...admin, page: 'settings' }).map((s) => s.id)
    const system = visibleSettingsSections({ ...admin, page: 'system' }).map((s) => s.id)
    const all = visibleSettingsSections(admin).map((s) => s.id)
    expect([...settings, ...system].sort()).toEqual([...all].sort())
    expect(settings.filter((id) => system.includes(id))).toEqual([])
  })

  it('restore lives where a person with no budget can reach it', () => {
    // The whole reason there are two pages: Settings sits inside the budget
    // shell, which redirects away when there is no budget to show.
    const restore = SETTINGS_SECTIONS.find((s) => s.id === 'data')
    expect(restore?.page).toBe('system')
    expect(restore?.needsBudget).toBeFalsy()
  })

  it('nothing on System needs a budget', () => {
    for (const s of SETTINGS_SECTIONS.filter((s) => s.page === 'system')) {
      expect(s.needsBudget, `'${s.id}' needs a budget but sits on System`).toBeFalsy()
    }
  })
})

describe('what a section says about itself', () => {
  it('sits in a group on its own page', () => {
    // A "This budget" heading over a System section would be a lie the nav
    // told on every visit.
    for (const s of SETTINGS_SECTIONS) {
      expect(SETTINGS_GROUPS[s.group].page, `'${s.id}' is grouped under another page`).toBe(s.page)
    }
  })

  it('has a sentence saying what it is for', () => {
    // The one-at-a-time view puts it under the title; a blank there is a
    // section nobody could explain.
    for (const s of SETTINGS_SECTIONS) {
      expect(s.description.length, `'${s.id}' has no description`).toBeGreaterThan(20)
    }
  })

  it('is grouped in list order, and empty groups are left out', () => {
    const groups = groupedSections(visibleSettingsSections({ budgetId: null, isAdmin: false }))
    expect(groups.map((g) => g.id)).toEqual([
      'you',
      'this-budget',
      'data',
      'installation',
      'connections',
    ])
    for (const g of groups) expect(g.sections.length).toBeGreaterThan(0)
    expect(groups[0].label).toBe('Personal')
  })
})

describe('the gates', () => {
  it('hide budget-scoped sections when no budget is open', () => {
    const ids = visibleSettingsSections({ budgetId: null, isAdmin: true }).map((s) => s.id)
    expect(ids).not.toContain('tags')
    expect(ids).not.toContain('budget-backups')
    expect(ids).toContain('data')
  })

  it('hide admin sections from everyone else', () => {
    const ids = visibleSettingsSections({ budgetId: 'b1', isAdmin: false }).map((s) => s.id)
    expect(ids).not.toContain('data')
    expect(ids).not.toContain('users')
    expect(ids).toContain('updates')
  })

  it('flag SimpleFIN only on the page that renders it', () => {
    const system = visibleSettingsSections({ ...admin, page: 'system', sfWarn: 'no key' })
    expect(system.find((s) => s.id === 'simplefin')?.warn).toBe('no key')
    const settings = visibleSettingsSections({ ...admin, page: 'settings', sfWarn: 'no key' })
    expect(settings.some((s) => s.warn)).toBe(false)
  })
})

describe('addresses', () => {
  it('spells a System address with the System path', () => {
    expect(sectionHref({ id: 'data', page: 'system' })).toBe('/system/data')
  })

  it('spells a Settings address with the Settings path', () => {
    expect(sectionHref({ id: 'appearance', page: 'settings' })).toBe('/settings/appearance')
  })

  it('reads the section back out of a path, and only its own page’s', () => {
    expect(sectionIdFromPath('settings', '/settings/budget')).toBe('budget')
    expect(sectionIdFromPath('settings', '/settings')).toBeNull()
    expect(sectionIdFromPath('settings', '/settings/')).toBeNull()
    expect(sectionIdFromPath('settings', '/system/data')).toBeNull()
  })

  it('round-trips: the path it spells is the path it reads', () => {
    for (const s of SETTINGS_SECTIONS) {
      expect(sectionIdFromPath(s.page, sectionHref(s))).toBe(s.id)
    }
  })
})

describe('the nav’s search', () => {
  const all = visibleSettingsSections(admin)

  it('finds a section by a keyword the palette would also find it by', () => {
    expect(filterSections(all, 'snapshot').map((s) => s.id)).toEqual(['budget-backups'])
  })

  it('finds a section by a word in its description', () => {
    expect(filterSections(all, 'ollama').map((s) => s.id)).toContain('ai')
  })

  it('is no filter when empty', () => {
    expect(filterSections(all, '  ')).toEqual(all)
  })
})

describe('neighbours', () => {
  const settings = visibleSettingsSections({ ...admin, page: 'settings' })

  it('are the sections either side in nav order', () => {
    const { prev, next } = neighbours(settings, 'budget')
    expect(prev?.id).toBe('account')
    expect(next?.id).toBe('accounts')
  })

  it('run out at the ends', () => {
    expect(neighbours(settings, settings[0].id).prev).toBeNull()
    expect(neighbours(settings, settings[settings.length - 1].id).next).toBeNull()
  })

  it('are nothing for a section that is not in the list', () => {
    expect(neighbours(settings, 'users')).toEqual({ prev: null, next: null })
  })
})
