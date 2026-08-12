import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

export interface UpdateStatus {
  enabled: boolean
  current_version: string
  latest_version: string | null
  update_available: boolean
  release_url: string | null
}

/** Opt-in update check. With the setting off (the default) the server answers
 * from local state and never contacts GitHub. */
export function useUpdateStatus() {
  return useQuery({
    queryKey: ['system', 'update-status'],
    queryFn: async () => {
      const { data } = await apiClient.get<UpdateStatus>('/system/update-status')
      return data
    },
    staleTime: 6 * 60 * 60 * 1000,
    retry: false,
  })
}
