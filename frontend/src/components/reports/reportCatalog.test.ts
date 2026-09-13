import { describe, expect, it } from 'vitest'
import { REPORT_TABS } from '../../stores/reportStore'
import { REPORT_CATALOG, REPORT_SECTIONS, reportScopeOf } from './reportCatalog'
import { SCOPE_COPY } from './reportScope'

describe('REPORT_CATALOG', () => {
  // The Record type already refuses a missing tab; this catches the runtime
  // shapes a type cannot — an entry for a tab that was removed, or blank copy.
  it('has exactly one entry per report tab', () => {
    expect(Object.keys(REPORT_CATALOG).sort()).toEqual(REPORT_TABS.map((t) => t.id).sort())
  })

  it('states a known scope and non-empty copy for every report and section', () => {
    for (const [id, entry] of [
      ...Object.entries(REPORT_CATALOG),
      ...Object.entries(REPORT_SECTIONS),
    ]) {
      expect(SCOPE_COPY[entry.scope], id).toBeTruthy()
      for (const field of [entry.summary, entry.counts, entry.leavesOut]) {
        expect(field.trim(), id).not.toBe('')
      }
    }
  })

  it('places every section inside a real tab', () => {
    const tabs = new Set(REPORT_TABS.map((t) => t.id))
    for (const section of Object.values(REPORT_SECTIONS)) expect(tabs.has(section.tab)).toBe(true)
  })

  it('gives a section its own scope rather than its tab’s', () => {
    // Payday Effect is drawn on the Day Patterns tab but ignores the account
    // filter that tab honours.
    expect(reportScopeOf('day-patterns')).toBe('on-budget-filterable')
    expect(reportScopeOf('payday-effect')).toBe('on-budget')
    expect(reportScopeOf('net-worth')).toBe('all-accounts')
  })
})
