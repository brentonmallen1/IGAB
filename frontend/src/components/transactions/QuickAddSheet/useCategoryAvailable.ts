import { useCallback, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { budgetMonthQuery, useBudgetMonth } from '../../../api/budgets'
import { useFormatters } from '../../../hooks/useFormatters'
import { balancesByCategory } from '../../../utils/categoryBalances'
import { addMonths } from '../../../utils/dates'
import type { CategoryBalance } from '../../../types'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/**
 * Each category's Available for the month the transaction is dated in — not
 * the month the budget page happens to be showing, and not today's: a receipt
 * entered on the 1st for the 30th belongs to last month's envelope.
 *
 * Every figure here is the server's. Nothing adds the transaction to a
 * balance: the "after" of a save is read back from the refetched month, so a
 * card envelope, a rollover or a future-dated row says whatever the server
 * decided it says.
 *
 * `budgetId` null keeps the month unfetched (the sheet is closed, or the
 * account is a tracking account whose rows carry no category).
 */
export function useCategoryAvailable(budgetId: string | null, date: string) {
  const qc = useQueryClient()
  const { formatMoney } = useFormatters()
  // A cleared date input is '' — no month to ask for, rather than "NaN-NaN-01".
  const month = ISO_DATE.test(date) ? addMonths(date, 0) : null
  const { data } = useBudgetMonth(month ? budgetId : null, month ?? '')
  const balances = useMemo(() => balancesByCategory(data), [data])

  /** "$240.00", or undefined where there is no figure to show: the month has
   *  not loaded, or the category is an Income one (served `available: null`). */
  const hintFor = useCallback(
    (categoryId: string | null): string | undefined => {
      const available = categoryId ? balances.get(categoryId)?.available : null
      return available === null || available === undefined ? undefined : formatMoney(available)
    },
    [balances, formatMoney]
  )

  /**
   * The category's balance as the server has it now. Called after the create
   * mutation resolves, whose onSuccess has already invalidated (and, for this
   * observed month, refetched) every budget month — so `fetchQuery` hands back
   * that refetch, or fetches if the entry was not being watched. Null when it
   * cannot say: never a stale or guessed figure.
   */
  const readServerBalance = useCallback(
    async (categoryId: string): Promise<CategoryBalance | null> => {
      if (!budgetId || !month) return null
      try {
        const fresh = await qc.fetchQuery(budgetMonthQuery(budgetId, month))
        return balancesByCategory(fresh).get(categoryId) ?? null
      } catch {
        return null
      }
    },
    [qc, budgetId, month]
  )

  return { balances, hintFor, readServerBalance }
}
