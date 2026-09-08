import { describe, expect, it } from 'vitest'
import { groundingNote } from './groundingNote'

const base = { figures: 0, grounded: 0, derived: 0, unsupported: [], lookups: 1 }

describe('groundingNote', () => {
  it('says nothing when there is nothing to say', () => {
    // A reassurance printed under every reply is wallpaper within a day.
    expect(groundingNote(null).tone).toBe('none')
    expect(groundingNote({ ...base, figures: 0 }).tone).toBe('none')
  })

  it('confirms an answer whose figures all came from the budget', () => {
    const note = groundingNote({ ...base, figures: 3, grounded: 3 })
    expect(note.tone).toBe('ok')
    expect(note.text).toContain('All 3 figures')
  })

  it('uses the singular for one figure', () => {
    expect(groundingNote({ ...base, figures: 1, grounded: 1 }).text).toContain('The figure')
  })

  it('never claims the answer is verified', () => {
    // The check proves a number appeared in the data, not that the answer
    // reasons about it correctly.
    const note = groundingNote({ ...base, figures: 2, grounded: 2 })
    expect(note.text.toLowerCase()).not.toContain('verified')
    expect(note.text.toLowerCase()).not.toContain('accurate')
    expect(note.text.toLowerCase()).not.toContain('correct')
  })

  it('names the figure that failed rather than counting it', () => {
    // "1 figure could not be checked" sends you hunting.
    const note = groundingNote({ ...base, figures: 2, grounded: 1, unsupported: ['$4,182.33'] })
    expect(note.tone).toBe('warn')
    expect(note.text).toContain('$4,182.33')
    expect(note.text).toContain("isn't")
  })

  it('pluralises several unsupported figures', () => {
    const note = groundingNote({
      ...base,
      figures: 3,
      unsupported: ['$10.00', '$20.00'],
    })
    expect(note.text).toContain('$10.00, $20.00')
    expect(note.text).toContain("aren't")
  })

  it('caps the named figures and counts the rest', () => {
    const note = groundingNote({
      ...base,
      figures: 6,
      unsupported: ['$1.00', '$2.00', '$3.00', '$4.00', '$5.00'],
    })
    expect(note.text).toContain('and 2 more')
  })

  it('calls out figures stated with no lookups at all', () => {
    const note = groundingNote({ ...base, figures: 2, unsupported: ['$5.00'], lookups: 0 })
    expect(note.tone).toBe('warn')
    expect(note.text).toContain('without looking anything up')
  })

  it('stays quiet when nothing was looked up and no figures were given', () => {
    expect(groundingNote({ ...base, figures: 0, lookups: 0 }).tone).toBe('none')
  })

  it('treats derived arithmetic as grounded', () => {
    // Adding two envelopes together must not read as invention.
    const note = groundingNote({ ...base, figures: 3, grounded: 2, derived: 1 })
    expect(note.tone).toBe('ok')
  })
})
