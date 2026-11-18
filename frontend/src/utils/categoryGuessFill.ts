/**
 * Whether the server's category guess may be written into an entry form.
 *
 * The add-transaction screens used to copy the payee's stored default into
 * the category the moment a payee was picked. That pre-fill was then sent
 * as an explicit choice, so the server's per-payee rule (backend
 * domain/category_guess.py) never ran for a hand-entered row. The screens
 * now show the server's own answer (`usePayeeCategoryGuess`) — and only
 * where the person has not said otherwise.
 *
 * The rule, in order:
 * - **The person chose** (picked a category, or "No category", or took an
 *   AI suggestion): never touched again.
 * - **The field holds the guess we wrote** (or is empty): follow the guess —
 *   a new amount or payee may move it, and a blank guess clears it, because
 *   blank is what Save would then file.
 * - **The field holds something else** (the row's own category, or one the
 *   screen was opened with): left alone.
 *
 * Returns the value to write, or `undefined` for "leave it".
 */
export interface GuessFillState {
  /** The category in the field now; '' and null both mean none. */
  current: string | null
  /** The guess this form last wrote, if any. */
  autoFilled: string | null
  /** The person picked a category (or none) themselves. */
  userChose: boolean
}

export function guessFill(state: GuessFillState, guess: string | null): string | null | undefined {
  if (state.userChose) return undefined
  const current = state.current || null
  const ours = current === null || current === state.autoFilled
  if (!ours) return undefined
  return guess === current ? undefined : guess
}
