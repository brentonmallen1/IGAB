import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { SimpleFINConnection } from '../types'

export function useSimpleFINConnections() {
  return useQuery({
    queryKey: ['simplefin-connections'],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINConnection[]>('/simplefin/connections')
      return data
    },
    staleTime: 30_000,
  })
}

export function useSetupSimpleFIN() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (setup_token: string) =>
      apiClient
        .post<SimpleFINConnection>('/simplefin/setup', { setup_token })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useUpdateSimpleFINInterval() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, sync_interval_hours }: { id: string; sync_interval_hours: number }) =>
      apiClient
        .put<SimpleFINConnection>(`/simplefin/connections/${id}`, { sync_interval_hours })
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useDeleteSimpleFINConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/simplefin/connections/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useSyncSimpleFIN(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (connectionId: string) =>
      apiClient
        .post<{ imported: number; skipped: number }>(
          `/simplefin/connections/${connectionId}/sync`,
          {},
          { params: { budget_id: budgetId } },
        )
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
    },
  })
}

export function useLinkSimpleFINAccount(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (simplefin_account_id: string) =>
      apiClient.post(`/accounts/${accountId}/link-simplefin`, { simplefin_account_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
}

export function useUnlinkSimpleFINAccount(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.delete(`/accounts/${accountId}/link-simplefin`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['accounts'] })
    },
  })
}

export function useSimpleFINRemoteAccounts(connectionId: string | null) {
  return useQuery({
    queryKey: ['simplefin-remote-accounts', connectionId],
    queryFn: async () => {
      const { data } = await apiClient.get<{ id: string; name: string }[]>(
        `/simplefin/connections/${connectionId}/accounts`,
      )
      return data
    },
    enabled: !!connectionId,
    staleTime: 60_000,
  })
}
