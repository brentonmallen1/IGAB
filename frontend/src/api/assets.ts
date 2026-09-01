/**
 * Assets: things the household owns whose worth is stated and dated.
 *
 * Every mutation invalidates the reports root as well — a value point moves
 * the net-worth line the moment it lands, the same coupling the liability
 * snapshot mutation documents.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

export interface Asset {
  id: string
  budget_id: string
  name: string
  asset_type: 'property' | 'vehicle' | 'other' | null
  /** The newest value point, as a pair that travels together — null until
   *  the first point is recorded (contributing nothing to net worth). The
   *  date is part of the figure: a self-reported number that moves net
   *  worth UP carries its provenance everywhere it appears. */
  current_value: number | null
  value_as_of: string | null
  created_at: string
  updated_at: string
}

export interface AssetValue {
  id: string
  asset_id: string
  date: string
  value: number
  source: string
}

export function useAssets(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.assets, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<Asset[]>(`/${budgetId}/assets`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useAssetValues(budgetId: string | null, assetId: string | null) {
  return useQuery({
    queryKey: [ROOT.assetValues, budgetId, assetId],
    queryFn: async () => {
      const { data } = await apiClient.get<AssetValue[]>(`/${budgetId}/assets/${assetId}/values`)
      return data
    },
    enabled: !!budgetId && !!assetId,
  })
}

function invalidateAssetData(qc: ReturnType<typeof useQueryClient>, budgetId: string) {
  qc.invalidateQueries({ queryKey: [ROOT.assets, budgetId] })
  qc.invalidateQueries({ queryKey: [ROOT.assetValues, budgetId] })
  // A value moves net worth; the link moves equity on the liability pages.
  qc.invalidateQueries({ queryKey: [ROOT.reports] })
  qc.invalidateQueries({ queryKey: [ROOT.liabilities, budgetId] })
  qc.invalidateQueries({ queryKey: [ROOT.accountHygiene] })
}

export function useCreateAsset(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      name: string
      asset_type?: string | null
      value?: number | null
      value_as_of?: string | null
    }) => {
      const { data } = await apiClient.post<Asset>(`/${budgetId}/assets`, body)
      return data
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}

export function useUpdateAsset(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: string; name?: string; asset_type?: string }) => {
      const { data } = await apiClient.patch<Asset>(`/${budgetId}/assets/${id}`, body)
      return data
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}

export function useDeleteAsset(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/${budgetId}/assets/${id}`)
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}

export function useAddAssetValue(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      assetId,
      value,
      date,
    }: {
      assetId: string
      value: number
      date?: string
    }) => {
      const { data } = await apiClient.post<AssetValue>(`/${budgetId}/assets/${assetId}/values`, {
        value,
        date,
      })
      return data
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}

export function useUpdateAssetValue(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      assetId,
      valueId,
      value,
    }: {
      assetId: string
      valueId: string
      value: number
    }) => {
      const { data } = await apiClient.patch<AssetValue>(
        `/${budgetId}/assets/${assetId}/values/${valueId}`,
        { value }
      )
      return data
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}

export function useDeleteAssetValue(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ assetId, valueId }: { assetId: string; valueId: string }) => {
      await apiClient.delete(`/${budgetId}/assets/${assetId}/values/${valueId}`)
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}

export function useLinkAsset(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      liabilityId,
      assetId,
    }: {
      liabilityId: string
      assetId: string | null
    }) => {
      const { data } = await apiClient.put(`/${budgetId}/liabilities/${liabilityId}/link-asset`, {
        asset_id: assetId,
      })
      return data
    },
    onSuccess: () => invalidateAssetData(qc, budgetId),
  })
}
