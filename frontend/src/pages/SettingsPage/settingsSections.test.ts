/**
 * The one registry behind two settings pages and the command palette.
 *
 * What it must hold: every section lives on exactly one page, the pages
 * partition the list, a section's address is spelled in one place, and the
 * gates (budget open, admin) apply the same way whichever reader asks.
 */
import { describe, expect, it } from 'vitest'
import {
  SETTINGS_PAGES,
  SETTINGS_SECTIONS,
  sectionHref,
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

describe('sectionHref', () => {
  it('spells a System address with the System path', () => {
    expect(sectionHref({ id: 'data', page: 'system' })).toBe('/system#data')
  })

  it('spells a Settings address with the Settings path', () => {
    expect(sectionHref({ id: 'appearance', page: 'settings' })).toBe('/settings#appearance')
  })
})
