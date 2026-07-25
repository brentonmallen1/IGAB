import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Payee } from '../types'

export interface PayeeWithCount extends Payee {
  transaction_count: number
}

export interface NearbyPayee {
  id: string
  name: string
  default_category_id: string | null
  distance_m: number
  visit_count: number
  last_date: string
}

export function useNearbyPayees(
  budgetId: string | null,
  coords: { latitude: number; longitude: number } | null
) {
  return useQuery({
    queryKey: ['nearbyPayees', budgetId, coords?.latitude, coords?.longitude],
    queryFn: async () => {
      const { data } = await apiClient.get<NearbyPayee[]>(`/${budgetId}/payees/nearby`, {
        params: { lat: coords!.latitude, lng: coords!.longitude },
      })
      return data
    },
    enabled: !!budgetId && !!coords,
    staleTime: 60_000,
  })
}

export function usePayees(budgetId: string | null) {
  return useQuery({
    queryKey: ['payees', budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<PayeeWithCount[]>(`/${budgetId}/payees`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCreatePayee(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      apiClient.post<Payee>(`/${budgetId}/payees`, { name }).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payees', budgetId] }),
  })
}

export function useUpdatePayee(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; default_category_id?: string; mapping_samples?: string | null }) =>
      apiClient.patch<Payee>(`/payees/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['payees', budgetId] }),
  })
}

export function useDeletePayee(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/payees/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payees', budgetId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}

export function useMergePayee(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ sourceId, targetId }: { sourceId: string; targetId: string }) =>
      apiClient.post(`/payees/${sourceId}/merge`, { target_id: targetId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payees', budgetId] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
}
