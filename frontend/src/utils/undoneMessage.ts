import type { UndoResponse } from '../api/changes'

type Skips = Pick<UndoResponse, 'skipped_change_ids'>

/**
 * What an undo left alone, said once.
 *
 * A bulk assign or Cover Overspending writes one budget move per envelope
 * under one batch, and the server takes back the moves it still can, leaving
 * any envelope the user has since assigned by hand exactly as they set it.
 * That is the right thing to do and the wrong thing to stay quiet about:
 * "Undone" over a grid where one envelope is still funded reads as a bug,
 * which is how the all-or-nothing version got reported in the first place.
 *
 * Null when nothing was skipped, which is every undo but these.
 */
export function skippedNote(result: Skips): string | null {
  const skipped = result.skipped_change_ids?.length ?? 0
  if (skipped === 0) return null
  return skipped === 1
    ? '1 envelope you changed since was left as you set it'
    : `${skipped} envelopes you changed since were left as you set them`
}

/**
 * The toast for an undo addressed by batch (the Undo button beside a bulk
 * assign). ⌘Z builds its own sentence — it names what it undid — and appends
 * `skippedNote` to it, so the two share the clause rather than the sentence.
 */
export function undoneMessage(result: Skips): string {
  const note = skippedNote(result)
  return note ? `Undone — ${note}` : 'Undone'
}
