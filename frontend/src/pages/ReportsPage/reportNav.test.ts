import { describe, expect, it } from 'vitest'
import { FAVORITES_LABEL, favoriteTabs, reportNav, toggleFavorite } from './reportNav'
import type { ReportTab } from '../../stores/reportStore'

describe('which row the nav draws', () => {
  it('draws the active report’s own group by default', () => {
    const nav = reportNav('seasonality', false, [])
    expect(nav.favorites).toBe(false)
    expect(nav.label).toBe('Spending')
    expect(nav.tabs.map((t) => t.id)).toContain('seasonality')
  })

  it('draws the starred row when the nav is on favourites', () => {
    const favorites: ReportTab[] = ['essentials', 'net-worth']
    const nav = reportNav('essentials', true, favorites)
    expect(nav.favorites).toBe(true)
    expect(nav.label).toBe(FAVORITES_LABEL)
    expect(nav.tabs.map((t) => t.id)).toEqual(favorites)
  })

  it('keeps the starred row across reports from different groups', () => {
    // The whole point: a starred report keeps its real group, so following
    // one from the starred row must not flip the nav to that group. The two
    // here are genuinely in different groups — Essentials and Cost of Living
    // are both Financial State now, since the pair is only useful read side
    // by side.
    const favorites: ReportTab[] = ['essentials', 'seasonality']
    expect(reportNav('seasonality', true, favorites).favorites).toBe(true)
  })

  it('falls back to the group when the active report is not starred', () => {
    // Unstarring the one you are looking at, a `?tab=` deep link, or a
    // persisted flag from a budget whose stars are gone — one rule, no
    // cleanup.
    const nav = reportNav('seasonality', true, ['essentials'])
    expect(nav.favorites).toBe(false)
    expect(nav.label).toBe('Spending')
  })

  it('falls back when nothing is starred at all', () => {
    expect(reportNav('essentials', true, []).favorites).toBe(false)
  })
})

describe('the starred list', () => {
  it('drops ids this build no longer has', () => {
    // The server stores the list and does not know what is in it, so a
    // renamed or removed report arrives as a string with no tab behind it.
    const tabs = favoriteTabs(['essentials', 'debts' as ReportTab, 'net-worth'])
    expect(tabs.map((t) => t.id)).toEqual(['essentials', 'net-worth'])
  })

  it('appends a new star rather than sorting it in', () => {
    // The row is a list the user built; the positions they reach for by
    // muscle memory must not move when they star something else.
    expect(toggleFavorite(['net-worth'], 'essentials')).toEqual(['net-worth', 'essentials'])
  })

  it('removes one without disturbing the rest', () => {
    const favorites: ReportTab[] = ['net-worth', 'essentials', 'savings']
    expect(toggleFavorite(favorites, 'essentials')).toEqual(['net-worth', 'savings'])
  })
})
