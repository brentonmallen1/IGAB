import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

export interface AccountTypeInfo {
  id: string
  budget_id: string
  key: string
  label: string
  classification: 'asset' | 'liability'
  default_on_budget: boolean
  description: string | null
  is_system: boolean
  sort_order: number
}

export interface AccountTypeCreate {
  label: string
  classification: 'asset' | 'liability'
  default_on_budget?: boolean
  description?: string | null
}

export interface AccountTypeUpdate {
  label?: string
  classification?: 'asset' | 'liability'
  default_on_budget?: boolean
  description?: string | null
  sort_order?: number
}

export function useAccountTypes(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.accountTypes, budgetId],
    queryFn: () =>
      apiClient.get<AccountTypeInfo[]>(`/${budgetId}/account-types`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCreateAccountType(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AccountTypeCreate) =>
      apiClient
        .post<AccountTypeInfo>(`/${budgetId}/account-types`, data)
        .then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.accountTypes, budgetId] }),
  })
}

export function useUpdateAccountType(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: AccountTypeUpdate & { id: string }) =>
      apiClient
        .patch<AccountTypeInfo>(`/${budgetId}/account-types/${id}`, data)
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.accountTypes, budgetId] })
      // classification edits cascade onto accounts' mirrors
      qc.invalidateQueries({ queryKey: [ROOT.accounts, budgetId] })
    },
  })
}

export function useDeleteAccountType(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (typeId: string) => apiClient.delete(`/${budgetId}/account-types/${typeId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.accountTypes, budgetId] }),
  })
}
