/**
 * A drill-down has to list exactly what the bar above it counted — no more.
 *
 * The three scope axes union on the server, which is right for the filter bar
 * and wrong for a drill in two opposite ways. Both produce the same symptom, a
 * panel whose total contradicts the bar that opened it, which is the one thing
 * a drill-down exists not to do.
 */
import { describe, expect, it } from 'vitest'
import { drillScope } from './drillScope'

const SCOPE = { categoryIds: ['c1'], tagIds: ['t1'], filterId: 'f1' }

describe('a chart drilling into its own categories', () => {
  it('sends only those, so the tag cannot widen them back out', () => {
    // A treemap tile is a subset of what the report already counted. Union the
    // tag back in and one $80 tile opens a list of everything tagged.
    expect(drillScope(SCOPE, ['housing-1', 'housing-2'])).toEqual({
      categoryIds: ['housing-1', 'housing-2'],
    })
  })

  it('holds even for an empty list, which means "these none"', () => {
    // The Cost of Living Uncategorized bucket passes no ids by design, but a
    // chart that computed an empty member list means an empty drill — not a
    // drill scoped by whatever the bar happens to say.
    expect(drillScope(SCOPE, [])).toEqual({ categoryIds: [] })
  })
})

describe('a chart drilling into a day, a month or a payee', () => {
  it('carries the whole scope, since it narrows by nothing itself', () => {
    expect(drillScope(SCOPE)).toEqual({
      categoryIds: ['c1'],
      tagIds: ['t1'],
      filterId: 'f1',
    })
  })

  it('sends nothing when the bar is unscoped', () => {
    // Undefined rather than empty arrays: the server reads "no scope asked
    // for" from their absence, and an empty list there would mean "a scope
    // that matched nothing" and return an empty panel.
    expect(drillScope({ categoryIds: [], tagIds: [], filterId: null })).toEqual({
      categoryIds: undefined,
      tagIds: undefined,
      filterId: undefined,
    })
  })

  it('carries whichever axes are actually set', () => {
    expect(drillScope({ tagIds: ['t1'] })).toEqual({
      categoryIds: undefined,
      tagIds: ['t1'],
      filterId: undefined,
    })
    expect(drillScope({ filterId: 'f1' })).toEqual({
      categoryIds: undefined,
      tagIds: undefined,
      filterId: 'f1',
    })
  })
})
