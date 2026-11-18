import { useCallback, useEffect, useRef, useState } from 'react'
import { usePayeeCategoryGuess } from '../api/payees'
import { guessFill } from '../utils/categoryGuessFill'
import { useDebouncedValue } from './useDebouncedValue'

/** Amount edits settle this long before the guess is asked again. */
export const GUESS_DEBOUNCE_MS = 250

interface Options {
  budgetId: string | null
  payeeId: string | null
  /** Signed amount in cents, or null while there is no amount yet. */
  cents: number | null
  /** False where no category may be offered (a tracking account, a split). */
  enabled: boolean
  /** The category field's value; '' and null both mean none. */
  categoryId: string | null
  setCategoryId: (id: string | null) => void
}

/**
 * Fill an entry form's category with what Save would file — the server's
 * per-payee rule — without ever overriding the person (utils/categoryGuessFill).
 *
 * Armed by `payeePicked(id)`: the guess follows a payee chosen in this form,
 * not one an existing row was opened with, which is when the old default
 * pre-fill ran too. Never blocks typing or Save: until the answer arrives
 * the field stays as it is, and a Save sent with no category is categorised
 * by the same rule on the server.
 */
export function useCategoryGuessFill({
  budgetId,
  payeeId,
  cents,
  enabled,
  categoryId,
  setCategoryId,
}: Options) {
  // The payee picked in this form; the guess runs while it is still the one
  // in the field.
  const [pickedPayeeId, setPickedPayeeId] = useState<string | null>(null)
  const autoFilled = useRef<string | null>(null)
  const userChose = useRef(false)

  const settledCents = useDebouncedValue(cents, GUESS_DEBOUNCE_MS)
  const asking = enabled && payeeId !== null && pickedPayeeId === payeeId
  const { data: guess } = usePayeeCategoryGuess(
    asking ? budgetId : null,
    asking ? payeeId : null,
    asking ? settledCents : null
  )

  useEffect(() => {
    if (!asking || guess === undefined) return
    const next = guessFill(
      { current: categoryId, autoFilled: autoFilled.current, userChose: userChose.current },
      guess
    )
    if (next === undefined) return
    autoFilled.current = next
    setCategoryId(next)
    // categoryId is read, not followed: a change the person makes is theirs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asking, guess])

  // No payee is a fresh start: a form reset, "add another", or the payee
  // cleared. A category the person chose is still in the field and still not
  // ours, so the next guess leaves it alone (utils/categoryGuessFill).
  useEffect(() => {
    if (payeeId !== null) return
    autoFilled.current = null
    userChose.current = false
  }, [payeeId])

  const payeePicked = useCallback((id: string) => setPickedPayeeId(id), [])
  const categoryChosen = useCallback(() => {
    userChose.current = true
  }, [])

  return { payeePicked, categoryChosen }
}
