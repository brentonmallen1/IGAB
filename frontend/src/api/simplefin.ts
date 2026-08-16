import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type {
  SimpleFINConnection,
  SimpleFINRateLimitStatus,
  SyncResult,
  TransactionMatch,
} from '../types'

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

export function useSimpleFINRateLimitStatus(connectionId: string | null) {
  return useQuery({
    queryKey: ['simplefin-rate-limit', connectionId],
    queryFn: async () => {
      const { data } = await apiClient.get<SimpleFINRateLimitStatus>(
        `/simplefin/connections/${connectionId}/status`,
      )
      return data
    },
    enabled: !!connectionId,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: 30_000,
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

export function useUpdateSimpleFINConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...updates
    }: {
      id: string
      sync_interval_hours?: number
      sync_enabled?: boolean
      daily_sync_time?: string | null
    }) =>
      apiClient
        .put<SimpleFINConnection>(`/simplefin/connections/${id}`, updates)
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
    mutationFn: ({
      connectionId,
      accountSimplefinId,
    }: {
      connectionId: string
      accountSimplefinId?: string
    }) =>
      apiClient
        .post<SyncResult>(
          `/simplefin/connections/${connectionId}/sync`,
          {},
          {
            params: {
              budget_id: budgetId,
              ...(accountSimplefinId ? { account_simplefin_id: accountSimplefinId } : {}),
            },
          },
        )
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      qc.invalidateQueries({ queryKey: ['accounts'] })
      qc.invalidateQueries({ queryKey: ['simplefin-connections'] })
      qc.invalidateQueries({ queryKey: ['simplefin-rate-limit'] })
      // Sync can queue review matches, create unapproved rows, and advance
      // cleared state — every "needs attention" surface must refetch.
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
      qc.invalidateQueries({ queryKey: ['pending-matches-account'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account'] })
      qc.invalidateQueries({ queryKey: ['reconcile-status'] })
      qc.invalidateQueries({ queryKey: ['budgetMonth'] })
    },
  })
}

export function useLinkSimpleFINAccount(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string | null }) =>
      apiClient.post(`/accounts/${accountId}/link-simplefin`, {
        simplefin_account_id: id,
        simplefin_account_name: name,
      }),
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

export function useUpdateAccountSimpleFINSettings(accountId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (simplefin_sync_enabled: boolean) =>
      apiClient.patch(`/accounts/${accountId}/simplefin-settings`, null, {
        params: { simplefin_sync_enabled },
      }),
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

export function usePendingMatchesForAccount(accountId: string | null) {
  return useQuery({
    queryKey: ['pending-matches-account', accountId],
    queryFn: async () => {
      const { data } = await apiClient.get<TransactionMatch[]>(
        `/accounts/${accountId}/pending-matches`,
      )
      return data
    },
    enabled: !!accountId,
    staleTime: 15_000,
  })
}

export function usePendingMatches(budgetId: string | null) {
  return useQuery({
    queryKey: ['simplefin-matches', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<TransactionMatch[]>('/simplefin/matches', {
        params: { budget_id: budgetId },
      })
      return data
    },
    enabled: !!budgetId,
    staleTime: 15_000,
  })
}

export function useAcceptMatch(accountId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (matchId: string) =>
      apiClient.post(`/simplefin/matches/${matchId}/accept`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
      qc.invalidateQueries({ queryKey: ['pending-matches-account', accountId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['all-transactions'] })
      // Accepting merges away the duplicate — cleared/working balances change
      qc.invalidateQueries({ queryKey: ['accounts'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count'] })
      qc.invalidateQueries({ queryKey: ['pending-review-count-account'] })
    },
  })
}

export function useRejectMatch(accountId?: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (matchId: string) =>
      apiClient.post(`/simplefin/matches/${matchId}/reject`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['simplefin-matches'] })
      qc.invalidateQueries({ queryKey: ['pending-matches-account', accountId] })
    },
  })
}
