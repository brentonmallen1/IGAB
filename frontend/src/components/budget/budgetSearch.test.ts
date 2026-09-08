import { describe, expect, it } from 'vitest'
import { isBudgetSearchActive, matchesBudgetSearch, parseBudgetSearch } from './budgetSearch'

const cat = (name: string, tags: string[] = []) => ({
  name,
  tags: tags.map((t) => ({ name: t })),
})

describe('parseBudgetSearch', () => {
  it('reads a bare query as free text', () => {
    expect(parseBudgetSearch('Rent')).toEqual({ text: 'rent', tagNames: [] })
  })

  it('reads the compact and spaced forms the same way', () => {
    expect(parseBudgetSearch('tag:essential')).toEqual({ text: '', tagNames: ['essential'] })
    expect(parseBudgetSearch('tag: essential')).toEqual({ text: '', tagNames: ['essential'] })
  })

  it('keeps a quoted tag name whole', () => {
    // The tokenizer is shared with the register precisely so this works the
    // same in both boxes; splitting on the space gave `tag:"Fixed` a needle
    // that matched by accident and left `Costs"` as free text.
    expect(parseBudgetSearch('tag:"Fixed Costs"')).toEqual({ text: '', tagNames: ['fixed costs'] })
  })

  it('collects several tags and the leftover text', () => {
    expect(parseBudgetSearch('tag:essential tag:fun rent')).toEqual({
      text: 'rent',
      tagNames: ['essential', 'fun'],
    })
  })

  it('ignores a half-typed trailing tag:', () => {
    // Mid-keystroke. Treating it as "match the empty tag name" would blank the
    // grid on the way to typing a real one.
    expect(parseBudgetSearch('tag:')).toEqual({ text: '', tagNames: [] })
    expect(isBudgetSearchActive(parseBudgetSearch('tag:'))).toBe(false)
  })

  it('is case-insensitive about the prefix itself', () => {
    expect(parseBudgetSearch('TAG:Essential').tagNames).toEqual(['essential'])
  })
})

describe('matchesBudgetSearch', () => {
  const empty = parseBudgetSearch('')

  it('matches everything when the box is empty', () => {
    expect(matchesBudgetSearch(cat('Rent'), empty, 'Housing')).toBe(true)
  })

  it('still matches the group name, as it always did', () => {
    const s = parseBudgetSearch('housing')
    expect(matchesBudgetSearch(cat('Rent'), s, 'Housing')).toBe(true)
  })

  it('matches a tag by substring, case-insensitively', () => {
    const s = parseBudgetSearch('tag:essen')
    expect(matchesBudgetSearch(cat('Rent', ['Essential']), s, 'Housing')).toBe(true)
    expect(matchesBudgetSearch(cat('Rent', ['Fun']), s, 'Housing')).toBe(false)
  })

  it('treats a category with no tags as unmatched, never as a wildcard', () => {
    const s = parseBudgetSearch('tag:essential')
    expect(matchesBudgetSearch({ name: 'Rent' }, s, 'Housing')).toBe(false)
    expect(matchesBudgetSearch(cat('Rent', []), s, 'Housing')).toBe(false)
  })

  it('ORs several tags', () => {
    const s = parseBudgetSearch('tag:essential tag:fun')
    expect(matchesBudgetSearch(cat('Rent', ['Essential']), s, 'Housing')).toBe(true)
    expect(matchesBudgetSearch(cat('Games', ['Fun']), s, 'Lifestyle')).toBe(true)
    expect(matchesBudgetSearch(cat('Gifts', ['Sinking']), s, 'Lifestyle')).toBe(false)
  })

  it('ANDs the tags with the free text', () => {
    const s = parseBudgetSearch('tag:essential rent')
    expect(matchesBudgetSearch(cat('Rent', ['Essential']), s, 'Housing')).toBe(true)
    // Right tag, wrong name.
    expect(matchesBudgetSearch(cat('Groceries', ['Essential']), s, 'Food')).toBe(false)
    // Right name, wrong tag.
    expect(matchesBudgetSearch(cat('Rent', ['Fun']), s, 'Housing')).toBe(false)
  })
})
