import { describe, expect, it } from 'vitest'
import { categoryFilterLabel, parseCategoryFilterCommand } from './categoryFilterCommand'

describe('parseCategoryFilterCommand', () => {
  it('reads the documented spelling', () => {
    expect(parseCategoryFilterCommand('filter: rent')).toEqual({ term: 'rent' })
  })

  it('does not insist on the space', () => {
    expect(parseCategoryFilterCommand('filter:rent')).toEqual({ term: 'rent' })
  })

  it('accepts a bare space, which is what people type', () => {
    expect(parseCategoryFilterCommand('filter groceries')).toEqual({ term: 'groceries' })
  })

  it('keeps a multi-word term whole', () => {
    expect(parseCategoryFilterCommand('filter: car insurance')).toEqual({
      term: 'car insurance',
    })
  })

  it('is case-insensitive on the keyword, not the term', () => {
    expect(parseCategoryFilterCommand('Filter: Rent')).toEqual({ term: 'Rent' })
  })

  it('reads a bare colon as "clear it"', () => {
    expect(parseCategoryFilterCommand('filter:')).toEqual({ term: '' })
  })

  it('leaves the bare word alone, so saved filters stay findable', () => {
    // Typing "filter" is how someone looks for their saved filters in the
    // list below; a row that filtered by nothing would bury them.
    expect(parseCategoryFilterCommand('filter')).toBeNull()
  })

  it('is not fooled by a word that merely starts with it', () => {
    expect(parseCategoryFilterCommand('filters')).toBeNull()
    expect(parseCategoryFilterCommand('filtering')).toBeNull()
  })

  it('ignores anything that is not a filter instruction', () => {
    expect(parseCategoryFilterCommand('groceries')).toBeNull()
    expect(parseCategoryFilterCommand('category: Rent')).toBeNull()
    expect(parseCategoryFilterCommand('')).toBeNull()
  })
})

describe('categoryFilterLabel', () => {
  it('names the term it will apply', () => {
    expect(categoryFilterLabel({ term: 'rent' })).toBe('Filter categories: rent')
  })

  it('says what an empty term does instead of showing a blank', () => {
    expect(categoryFilterLabel({ term: '' })).toBe('Clear the category filter')
  })
})
