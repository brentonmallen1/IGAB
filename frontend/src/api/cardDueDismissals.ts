import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'
import { today } from '../utils/dates'
import type { CardDueReminder, CardDueState } from '../utils/paymentDue'

/**
 * Card-bill reminders the household has dismissed — stored on the server so a
 * bill dismissed on one device stays dismissed on the other
 * (backend `services/card_due_dismissals.py`).
 *
 * A dismissal is of one due date in one state, never of a card: dismissing
 * "due" does not hide the "past due" that may follow for the same date, and
 * dismissing one date never silences the next. Only the banner reads these;
 * the credit-cards strip is not dismissible.
 */
export interface CardDueDismissal {
  account_id: string
  due_date: string
  state: CardDueState
}

export function useCardDueDismissals(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.cardDueDismissals, budgetId],
    queryFn: () =>
      apiClient.get<CardDueDismissal[]>(`/${budgetId}/card-due-dismissals`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useDismissCardDue(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ accountId, reminder }: { accountId: string; reminder: CardDueReminder }) =>
      apiClient
        .put<CardDueDismissal[]>(`/${budgetId}/card-due-dismissals`, {
          account_id: accountId,
          due_date: reminder.dueDate,
          state: reminder.state,
          // The server prunes dismissals older than 60 days against this.
          client_today: today(),
        })
        .then((r) => r.data),
    // The PUT answers with every dismissal still on file, so the banner hides
    // without waiting on a refetch.
    onSuccess: (rows) => {
      qc.setQueryData([ROOT.cardDueDismissals, budgetId], rows)
      // Recorded in the change log: the activity feed has a new row, and ⌘Z
      // can now take this back.
      qc.invalidateQueries({ queryKey: [ROOT.changes] })
    },
  })
}
