import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Account, AccountType } from '../types'

export interface AccountCreate {
  name: string
  account_type: AccountType
  on_budget?: boolean
  note?: string
  sort_order?: number
}

export async function fetchAccounts(budgetId: string, include_closed = false): Promise<Account[]> {
  const { data } = await apiClient.get<Account[]>(`/${budgetId}/accounts`, {
    params: { include_closed },
  })
  return data
}

export function useAccounts(budgetId: string | null, options?: { includeClosed?: boolean }) {
  const includeClosed = options?.includeClosed ?? false
  return useQuery({
    queryKey: ['accounts', budgetId, { includeClosed }],
    queryFn: () => fetchAccounts(budgetId!, includeClosed),
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useCreateAccount(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AccountCreate) =>
      apiClient.post<Account>(`/${budgetId}/accounts`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
    },
  })
}

export function useUpdateAccount(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<Account> & { id: string }) =>
      apiClient.patch<Account>(`/accounts/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
    },
  })
}

export function useDeleteAccount(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    // `liability` decides what becomes of the debt a liability account was
    // tracking: kept as a manually tracked one (the default and the
    // non-destructive branch) or removed with the account.
    mutationFn: ({
      accountId,
      liability = 'keep',
    }: {
      accountId: string
      liability?: 'keep' | 'delete'
    }) => apiClient.delete(`/accounts/${accountId}`, { params: { liability } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts', budgetId] })
      // Either disposition rewrites the companion, and both liability views
      // read it — the sidebar's debt section included.
      qc.invalidateQueries({ queryKey: ['liabilities', budgetId] })
    },
  })
}

export function useScanDuplicates() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (accountId: string) =>
      apiClient
        .post<{ created: number }>(`/accounts/${accountId}/scan-duplicates`)
        .then((r) => r.data),
    onSuccess: (_data, accountId) => {
      qc.invalidateQueries({ queryKey: ['pending-matches-account', accountId] })
    },
  })
}
