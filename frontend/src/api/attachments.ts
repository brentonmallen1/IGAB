import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { downscaleForUpload } from '../utils/imageUpload'
import { confirmAsync } from '../stores/confirmStore'
import { ROOT } from './queryKeys'

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

/** What the attachment endpoints accept: images plus PDF receipts/bills. */
export const ATTACHMENT_ACCEPT = 'image/*,application/pdf'

export function isAttachableFile(file: File): boolean {
  return file.type.startsWith('image/') || file.type === 'application/pdf'
}

export function isPdfAttachment(a: Pick<Attachment, 'content_type'>): boolean {
  return a.content_type === 'application/pdf'
}

const blobCache = new Map<string, string>()

export async function fetchAttachmentBlob(
  attachmentId: string,
  thumbnail = false
): Promise<string> {
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

/** Drop cached blob URLs for an attachment whose bytes changed (e.g. rotate). */
export function invalidateAttachmentBlob(attachmentId: string) {
  for (const thumbnail of [true, false]) {
    const cacheKey = `${attachmentId}-${thumbnail}`
    const url = blobCache.get(cacheKey)
    if (url) {
      URL.revokeObjectURL(url)
      blobCache.delete(cacheKey)
    }
  }
}

export function useRotateAttachment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { attachmentId: string; degrees: 90 | 180 | 270 }) => {
      const { data } = await apiClient.post<Attachment>(
        `/attachments/${vars.attachmentId}/rotate`,
        { degrees: vars.degrees }
      )
      return data
    },
    onSuccess: (data) => {
      invalidateAttachmentBlob(data.id)
      qc.invalidateQueries({ queryKey: [ROOT.attachmentBlob, data.id] })
      qc.invalidateQueries({ queryKey: [ROOT.attachments, data.transaction_id] })
    },
  })
}

/** The stored file is a WebP re-encode for images (PDFs are kept verbatim) —
 * download under the original base name with the real extension. */
export function attachmentDownloadName(
  a: Pick<Attachment, 'original_filename' | 'content_type'>
): string {
  if (isPdfAttachment(a)) {
    return /\.pdf$/i.test(a.original_filename) ? a.original_filename : `${a.original_filename}.pdf`
  }
  const base = a.original_filename.replace(/\.[^.]+$/, '')
  return `${base || a.original_filename}.webp`
}

export async function downloadAttachment(
  a: Pick<Attachment, 'id' | 'original_filename' | 'content_type'>
): Promise<void> {
  const url = await fetchAttachmentBlob(a.id)
  const link = document.createElement('a')
  link.href = url
  link.download = attachmentDownloadName(a)
  document.body.appendChild(link)
  link.click()
  link.remove()
}

export function useAttachments(transactionId: string | null) {
  return useQuery({
    queryKey: [ROOT.attachments, transactionId],
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
      // Downscaled at the API layer so every entry point (panel, drag-drop,
      // camera) benefits — a 12MP original is pointless over cellular when
      // the server stores a 2048px re-encode anyway. Falls back to the
      // original on any decode uncertainty.
      formData.append('file', await downscaleForUpload(file))
      const { data } = await apiClient.post<Attachment>(
        `/transactions/${transactionId}/attachments`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.attachments, transactionId] })
      qc.invalidateQueries({ queryKey: [ROOT.attachmentCheck] })
    },
  })
}

export function useDeleteAttachment(transactionId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (attachmentId: string) => apiClient.delete(`/attachments/${attachmentId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.attachments, transactionId] })
      qc.invalidateQueries({ queryKey: [ROOT.attachmentCheck] })
    },
  })
}

/**
 * Sequential multi-file upload for flows where the transaction is created
 * first (quick-add). Failures don't abort the batch — the transaction is the
 * money record and always wins; callers surface `failed` and let the user
 * retry from the editor.
 */
export async function uploadFilesToTransaction(
  transactionId: string,
  files: File[]
): Promise<{ ok: number; failed: File[] }> {
  let ok = 0
  const failed: File[] = []
  for (const file of files) {
    try {
      const formData = new FormData()
      // Same API-layer downscale as useUploadAttachment — see there.
      formData.append('file', await downscaleForUpload(file))
      await apiClient.post(`/transactions/${transactionId}/attachments`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      ok++
    } catch {
      failed.push(file)
    }
  }
  return { ok, failed }
}

/**
 * Confirm a transaction delete, warning about attached receipt images.
 * Attachment files are removed for good after the deletion grace period,
 * so the user should know images go down with the transaction.
 */
export async function confirmDeleteTransaction(transactionId: string): Promise<boolean> {
  let detail: string | undefined
  try {
    const { data } = await apiClient.get<Attachment[]>(`/transactions/${transactionId}/attachments`)
    if (data.length === 1) {
      detail = 'The attached receipt image will be deleted with it.'
    } else if (data.length > 1) {
      detail = `The ${data.length} attached receipt images will be deleted with it.`
    }
  } catch {
    // Count is best-effort; the plain confirmation still protects the delete.
  }
  return confirmAsync({
    title: 'Delete this transaction?',
    message: detail,
    confirmLabel: 'Delete',
    destructive: true,
  })
}

export function useCheckAttachments(transactionIds: string[]) {
  return useQuery({
    queryKey: [ROOT.attachmentCheck, transactionIds],
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
    queryKey: [ROOT.attachmentBlob, attachmentId, thumbnail],
    queryFn: () => fetchAttachmentBlob(attachmentId!, thumbnail),
    enabled: !!attachmentId,
    staleTime: Infinity,
  })
}
