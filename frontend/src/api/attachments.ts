import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface Attachment {
  id: string
  transaction_id: string
  filename: string
  original_filename: string
  content_type: string
  file_size: number
  width: number | null
  height: number | null
  created_at: string
}

const blobCache = new Map<string, string>()

export async function fetchAttachmentBlob(attachmentId: string, thumbnail = false): Promise<string> {
  const cacheKey = `${attachmentId}-${thumbnail}`
  if (blobCache.has(cacheKey)) return blobCache.get(cacheKey)!

  const params = thumbnail ? '?thumbnail=true' : ''
  const response = await apiClient.get(`/attachments/${attachmentId}${params}`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  blobCache.set(cacheKey, url)
  return url
}

export function getAttachmentUrl(attachmentId: string, thumbnail = false): string {
  const cacheKey = `${attachmentId}-${thumbnail}`
  return blobCache.get(cacheKey) ?? ''
}

export function useAttachments(transactionId: string | null) {
  return useQuery({
    queryKey: ['attachments', transactionId],
    queryFn: async () => {
      const { data } = await apiClient.get<Attachment[]>(
        `/transactions/${transactionId}/attachments`
      )
      return data
    },
    enabled: !!transactionId,
    staleTime: 60_000,
  })
}

export function useUploadAttachment(transactionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await apiClient.post<Attachment>(
        `/transactions/${transactionId}/attachments`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attachments', transactionId] })
      qc.invalidateQueries({ queryKey: ['attachmentCheck'] })
    },
  })
}

export function useDeleteAttachment(transactionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (attachmentId: string) =>
      apiClient.delete(`/attachments/${attachmentId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['attachments', transactionId] })
      qc.invalidateQueries({ queryKey: ['attachmentCheck'] })
    },
  })
}

export function useCheckAttachments(transactionIds: string[]) {
  return useQuery({
    queryKey: ['attachmentCheck', transactionIds],
    queryFn: async () => {
      const { data } = await apiClient.post<Record<string, boolean>>(
        '/transactions/attachments/check',
        transactionIds
      )
      return data
    },
    enabled: transactionIds.length > 0,
    staleTime: 30_000,
  })
}

export function useAttachmentUrl(attachmentId: string | null, thumbnail = false) {
  return useQuery({
    queryKey: ['attachmentBlob', attachmentId, thumbnail],
    queryFn: () => fetchAttachmentBlob(attachmentId!, thumbnail),
    enabled: !!attachmentId,
    staleTime: Infinity,
  })
}
