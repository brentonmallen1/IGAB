import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'
import { today } from '../utils/dates'
import type { CardDueKey } from '../utils/paymentDue'

/**
 * The household's card-bill keys, stored on the server so what one device
 * says the other device knows (backend `services/card_due_dismissals.py`).
 *
 * Two kinds in one store:
 *
 * - **A dismissal** (`due` / `past_due`) is of one due date in one state,
 *   never of a card: dismissing "due" does not hide the "past due" that may
 *   follow for the same date, and dismissing one date never silences the
 *   next. Only the banner reads these (`bannerLines`).
 * - **A bill marked paid** (`paid`) is read by the reminder rule itself
 *   (`reminderForCard`), so the banner, the credit-cards strip and the terms
 *   header all see that bill as settled, and the next due date reminds as
 *   usual.
 *
 * Every key is recorded in the change log, so ⌘Z — or the toast's Undo —
 * takes it back.
 */
export type CardDueDismissal = CardDueKey

export function useCardDueDismissals(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.cardDueDismissals, budgetId],
    queryFn: () =>
      apiClient.get<CardDueDismissal[]>(`/${budgetId}/card-due-dismissals`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

/** Store one key: dismiss a reminder in its state, or mark its bill paid. */
export function useRecordCardDue(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      accountId,
      dueDate,
      state,
    }: {
      accountId: string
      dueDate: string
      state: CardDueKey['state']
    }) =>
      apiClient
        .put<CardDueDismissal[]>(`/${budgetId}/card-due-dismissals`, {
          account_id: accountId,
          due_date: dueDate,
          state,
          // The server prunes old keys against this.
          client_today: today(),
        })
        .then((r) => r.data),
    // The PUT answers with every key still on file, so the banner and the
    // strip update without waiting on a refetch.
    onSuccess: (rows) => {
      qc.setQueryData([ROOT.cardDueDismissals, budgetId], rows)
      // Recorded in the change log: the activity feed has a new row, and ⌘Z
      // can now take this back.
      qc.invalidateQueries({ queryKey: [ROOT.changes] })
    },
  })
}
