/**
 * What an undo says it left alone.
 *
 * The report behind this: a bulk assign landed wrong, the user fixed one
 * envelope by hand, and undo then reverted nothing at all. The server now
 * takes back every move it still can and leaves the hand-set envelope alone —
 * which is only honest if the toast says so, since a grid with one envelope
 * still funded under a plain "Undone" reads exactly like the old bug.
 */
import { describe, expect, it } from 'vitest'
import { skippedNote, undoneMessage } from './undoneMessage'

describe('skippedNote', () => {
  it('says nothing when the undo took everything back', () => {
    expect(skippedNote({ skipped_change_ids: [] })).toBeNull()
  })

  it('names one left-alone envelope in the singular', () => {
    expect(skippedNote({ skipped_change_ids: ['a'] })).toBe(
      '1 envelope you changed since was left as you set it'
    )
  })

  it('pluralises', () => {
    expect(skippedNote({ skipped_change_ids: ['a', 'b', 'c'] })).toContain('3 envelopes')
  })

  it('treats a missing field as nothing skipped, never as a crash', () => {
    // Older servers, and every undo response that predates the field.
    expect(skippedNote({} as { skipped_change_ids: string[] })).toBeNull()
  })
})

describe('undoneMessage', () => {
  it('is the plain word when nothing was skipped', () => {
    expect(undoneMessage({ skipped_change_ids: [] })).toBe('Undone')
  })

  it('carries the same clause ⌘Z appends, rather than a second wording', () => {
    const result = { skipped_change_ids: ['a', 'b'] }
    expect(undoneMessage(result)).toBe(`Undone — ${skippedNote(result)}`)
  })
})
