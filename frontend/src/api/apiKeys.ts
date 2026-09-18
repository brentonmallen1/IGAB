import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'
import { ROOT } from './queryKeys'

/**
 * Read-only keys for reaching a budget from an assistant.
 *
 * Not the session token. That lasts 30 minutes, and the refresh token behind
 * it can mint full WRITE access to everything its owner has — handing either
 * to an MCP client would be handing it the whole budget.
 */
export interface ApiKey {
  id: string
  name: string
  /** The first characters, kept in the clear. Enough to tell two keys apart
   *  in a list and far too few to reconstruct one — the server stored a hash
   *  and nothing else. */
  prefix: string
  scopes: string
  budget_ids: string[]
  created_at: string
  last_used_at: string | null
  /** Revoked keys stay listed: a key that turns up in a config file or a log
   *  has to be identifiable after it stops working. */
  revoked_at: string | null
}

export interface ApiKeyCreated extends ApiKey {
  /** The only time this is ever returned. Show it once, say so, and never
   *  store it anywhere the page can read again. */
  key: string
}

export function useApiKeys() {
  return useQuery({
    queryKey: [ROOT.apiKeys],
    queryFn: async () => (await apiClient.get<ApiKey[]>('/api-keys')).data,
  })
}

export function useCreateApiKey() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { name: string; budget_ids: string[] }) =>
      (await apiClient.post<ApiKeyCreated>('/api-keys', payload)).data,
    onSuccess: () => client.invalidateQueries({ queryKey: [ROOT.apiKeys] }),
  })
}

export function useRevokeApiKey() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (keyId: string) => {
      await apiClient.delete(`/api-keys/${keyId}`)
    },
    onSuccess: () => client.invalidateQueries({ queryKey: [ROOT.apiKeys] }),
  })
}
