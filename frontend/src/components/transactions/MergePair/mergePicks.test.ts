import { describe, expect, it } from 'vitest'
import type { MergeChoice, MergePreview } from '../../../types'
import { hasChoices, isKept, pairLabels, pick, pickAll, suppliesAll } from './mergePicks'

const choice = (source: string | null, choosable = true): MergeChoice => ({ source, choosable })

function preview(choices: Partial<MergePreview['choices']> = {}): MergePreview {
  return {
    choices: {
      date: choice('a', false),
      payee: choice('a', false),
      category: choice('a', false),
      memo: choice(null, false),
      ...choices,
    },
  } as MergePreview
}

describe('picking a value', () => {
  it('takes the clicked row for a one-or-the-other field', () => {
    expect(pick({}, 'payee', choice('a'), 'b', 'a')).toEqual({ payee: 'b' })
    expect(pick({ date: 'a' }, 'category', choice('a'), 'b', 'a')).toEqual({
      date: 'a',
      category: 'b',
    })
  })

  it('changes nothing for a field that is not a choice', () => {
    const keep = { payee: 'a' }
    expect(pick(keep, 'payee', choice('a', false), 'b', 'a')).toBe(keep)
  })

  it('takes a memo out when both are in', () => {
    // Two different memos are joined by default; clicking one drops it.
    expect(pick({}, 'memo', choice('both'), 'a', 'b')).toEqual({ memo: 'b' })
  })

  it('puts a memo back beside the other', () => {
    expect(pick({ memo: 'b' }, 'memo', choice('b'), 'a', 'b')).toEqual({ memo: 'both' })
  })

  it('will not take the last memo out', () => {
    // A merge never drops a value for nothing: one of the two stays.
    const keep = { memo: 'a' }
    expect(pick(keep, 'memo', choice('a'), 'a', 'b')).toBe(keep)
  })
})

describe('reading the preview', () => {
  it('counts a row as kept when its value is in the result', () => {
    expect(isKept(choice('a'), 'a')).toBe(true)
    expect(isKept(choice('a'), 'b')).toBe(false)
    expect(isKept(choice('both'), 'a')).toBe(true)
    expect(isKept(choice('both'), 'b')).toBe(true)
    expect(isKept(choice(null), 'a')).toBe(false)
  })

  it('knows whether anything is a choice at all', () => {
    expect(hasChoices(preview())).toBe(false)
    expect(hasChoices(preview({ memo: choice('both') }))).toBe(true)
  })

  it('"use all" picks this row for every field that is a choice, and only those', () => {
    const p = preview({ payee: choice('a'), memo: choice('both') })
    expect(pickAll({ date: 'a' }, p, 'b')).toEqual({ date: 'a', payee: 'b', memo: 'b' })
  })

  it('knows when a row already supplies everything', () => {
    const p = preview({ payee: choice('a'), memo: choice('both') })
    expect(suppliesAll(p, 'a')).toBe(false) // the memo is still both
    expect(suppliesAll(preview({ payee: choice('a'), memo: choice('a') }), 'a')).toBe(true)
    expect(suppliesAll(preview({ payee: choice('a'), memo: choice('a') }), 'b')).toBe(false)
  })
})

describe('naming the two cards', () => {
  const bank = { has_sync_source: true, sync_source: 'simplefin' }
  const typed = { has_sync_source: false, sync_source: null }

  it('names a bank row and a hand-entered one for where they came from', () => {
    expect(pairLabels(typed, bank)).toEqual(['Entered by hand', 'From the bank'])
    expect(pairLabels(bank, typed)).toEqual(['From the bank', 'Entered by hand'])
  })

  it('tells two of a kind apart by position', () => {
    expect(pairLabels(typed, typed)).toEqual(['First transaction', 'Second transaction'])
    expect(pairLabels(bank, bank)).toEqual(['First transaction', 'Second transaction'])
  })
})
