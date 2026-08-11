import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface AppSetting {
  key: string
  value: string | null
  /** Whether a stored override exists (vs env/default) */
  is_overridden?: boolean | null
  default_value?: string | null
}

export async function fetchSettings(): Promise<AppSetting[]> {
  const { data } = await apiClient.get<AppSetting[]>('/settings')
  return data
}

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
    staleTime: 60_000,
  })
}

export function useUpdateSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      apiClient.put<AppSetting>(`/settings/${key}`, { value }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
    },
  })
}

/** Remove a stored override — the setting reverts to its default. */
export function useResetSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) =>
      apiClient.delete<AppSetting>(`/settings/${key}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
    },
  })
}
