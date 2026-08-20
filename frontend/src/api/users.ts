import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface ManagedUser {
  id: string
  email: string
  display_name: string | null
  is_admin: boolean
  is_active: boolean
  /** Credential owned by ADMIN_PASSWORD — no in-app reset/deactivate. */
  is_env_admin: boolean
}

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const { data } = await apiClient.get<ManagedUser[]>('/users')
      return data
    },
  })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { email: string; password: string; display_name?: string | null }) =>
      apiClient.post<ManagedUser>('/users', body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string
      display_name?: string | null
      is_active?: boolean
      /** Admin password reset. */
      password?: string
    }) => apiClient.patch<ManagedUser>(`/users/${id}`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}
