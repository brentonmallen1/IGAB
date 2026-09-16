import { describe, expect, it } from 'vitest'
import { ASIDE_ANCHORS, asideHref, guideTabHref } from './guideLinks'

describe('guide links', () => {
  it('addresses a tab, with a section when one is named', () => {
    expect(guideTabHref('money')).toBe('/guide?tab=money')
    expect(guideTabHref('aside', 'which-tag')).toBe('/guide?tab=aside#which-tag')
  })

  it('addresses every section of Setting money aside', () => {
    expect(ASIDE_ANCHORS.map(asideHref)).toEqual([
      '/guide?tab=aside#savings-modes',
      '/guide?tab=aside#which-tag',
      '/guide?tab=aside#emergency-fund',
      '/guide?tab=aside#sinking-funds',
      '/guide?tab=aside#means-trend',
      '/guide?tab=aside#savings-report',
    ])
  })
})
