import { describe, expect, it } from 'vitest'
import { gridNarrowing } from './gridNarrowing'

const none = { status: null, savedFilter: null, search: '', view: null }

describe('gridNarrowing', () => {
  it('is nothing when the grid shows everything', () => {
    expect(gridNarrowing(none)).toEqual([])
  })

  it('names each thing narrowing the grid, in order', () => {
    expect(
      gridNarrowing({
        status: 'overspent',
        savedFilter: null,
        search: ' groc ',
        view: 'Bills first',
      })
    ).toEqual([
      { key: 'status', label: 'Overspent' },
      { key: 'search', label: '“groc”' },
      { key: 'view', label: 'View: Bills first' },
    ])
  })

  it('does not count a search of only spaces', () => {
    expect(gridNarrowing({ ...none, search: '   ' })).toEqual([])
  })

  it('takes resolved names, so an id that names nothing narrows nothing', () => {
    expect(gridNarrowing({ ...none, savedFilter: null, view: null })).toEqual([])
  })
})
