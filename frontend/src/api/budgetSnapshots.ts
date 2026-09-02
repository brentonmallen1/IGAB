/**
 * Per-budget snapshots: one budget in one file.
 *
 * Distinct from `backups.ts`, which is the whole installation in one pg_dump
 * and is admin-only. These are budget-scoped, which is what makes "show me
 * the backups for the budget I'm in" answerable rather than a relabelled
 * global list.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
import { invalidateAfterImport } from './invalidateAfterImport'
import { downloadAuthed } from '../utils/exportFile'
import { ROOT } from './queryKeys'

export interface BudgetSnapshotFile {
  name: string
  size_bytes: number
  modified_at: string
}

export interface SnapshotCreated {
  name: string
  size_bytes: number
  budget_name: string
  exported_at: string
  row_counts: Record<string, number>
  attachments_omitted: number
}

export interface SnapshotInspection {
  format: string
  format_version: number
  alembic_revision: string
  app_version: string
  exported_at: string
  budget_name: string
  source_budget_id: string
  row_counts: Record<string, number>
  attachments_omitted: number
  ok: boolean
  refusals: string[]
  warnings: string[]
}

export interface SnapshotImportResult {
  budget_id: string
  budget_name: string
  row_counts: Record<string, number>
  attachments_omitted: number
  attachments_dropped: number
  warnings: string[]
}

/**
 * The largest snapshot the server will accept, in bytes.
 *
 * Must match `client_max_body_size` in frontend/nginx/default.conf.template —
 * nginx rejects anything larger with a bare 413 that never reaches FastAPI,
 * so the SPA would have nothing to explain. `snapshotSizeLimit.test.ts` reads
 * the nginx template and fails if the two drift.
 */
export const MAX_SNAPSHOT_BYTES = 200 * 1024 * 1024

export function tooLargeMessage(bytes: number): string | null {
  if (bytes <= MAX_SNAPSHOT_BYTES) return null
  const mb = Math.ceil(bytes / (1024 * 1024))
  const limit = MAX_SNAPSHOT_BYTES / (1024 * 1024)
  return `That file is ${mb} MB; the limit is ${limit} MB.`
}

export function useBudgetSnapshots(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.budgetSnapshots, budgetId],
    enabled: !!budgetId,
    queryFn: async () => {
      const { data } = await apiClient.get<BudgetSnapshotFile[]>(`/budgets/${budgetId}/snapshots`)
      return data
    },
  })
}

export function useCreateBudgetSnapshot(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<SnapshotCreated>(`/budgets/${budgetId}/snapshots`)
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.budgetSnapshots, budgetId] })
      toast.success('Snapshot saved')
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not save a snapshot')),
  })
}

export function useDeleteBudgetSnapshot(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => apiClient.delete(`/budgets/${budgetId}/snapshots/${name}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.budgetSnapshots, budgetId] })
      toast.success('Snapshot deleted')
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not delete that snapshot')),
  })
}

/** One spelling of "this budget's name as a filename". Both download paths
 *  use it, so the two files sort together and each names its format — a
 *  bare-UUID filename is how a snapshot ends up fed to the YNAB importer. */
function budgetSlug(budgetName: string): string {
  const slug = budgetName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
  return slug || 'budget'
}

/** A readable, portable export — YNAB-shaped, so a spreadsheet opens it and
 *  IGAB's own YNAB importer reads it back. Lossy, and the file says so. */
export function downloadBudgetExport(budgetId: string, budgetName: string): Promise<void> {
  return downloadAuthed(
    `/budgets/${budgetId}/export?format=ynab`,
    `${budgetSlug(budgetName)}-ynab-export.zip`
  )
}

/** Export now and hand the file straight to the browser. Named after the
 *  budget, with the format in the suffix — like the kept-snapshot files. */
export function downloadSnapshotNow(budgetId: string, budgetName: string): Promise<void> {
  return downloadAuthed(`/budgets/${budgetId}/snapshot`, `${budgetSlug(budgetName)}.igab.zip`)
}

export function downloadKeptSnapshot(budgetId: string, name: string): Promise<void> {
  return downloadAuthed(`/budgets/${budgetId}/snapshots/${name}`, name)
}

function asForm(file: File, fields: Record<string, string> = {}): FormData {
  const form = new FormData()
  form.append('file', file)
  for (const [key, value] of Object.entries(fields)) form.append(key, value)
  return form
}

/** Read a file's manifest and verdict. Writes nothing — this is what makes
 *  "check before you restore" a real option rather than an encouragement. */
export async function inspectSnapshot(file: File): Promise<SnapshotInspection> {
  const { data } = await apiClient.post<SnapshotInspection>(
    '/budgets/snapshot/inspect',
    asForm(file)
  )
  return data
}

export function useImportSnapshot() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, name }: { file: File; name?: string }) => {
      const { data } = await apiClient.post<SnapshotImportResult>(
        '/budgets/import-snapshot',
        asForm(file, name ? { name } : {})
      )
      return data
    },
    onSuccess: (result) => {
      invalidateAfterImport(qc, result.budget_id)
      toast.success(`Imported as "${result.budget_name}"`)
    },
    onError: (err) => toast.error(apiErrorMessage(err, 'Could not import that snapshot')),
  })
}

export function useRestoreSnapshot(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      file,
      confirmName,
      preSnapshot,
    }: {
      file: File
      confirmName: string
      preSnapshot: boolean
    }) => {
      const { data } = await apiClient.post<SnapshotImportResult>(
        `/budgets/${budgetId}/snapshot/restore`,
        asForm(file, { confirm_name: confirmName, pre_snapshot: String(preSnapshot) })
      )
      return data
    },
    onSuccess: (result) => {
      invalidateAfterImport(qc, result.budget_id)
      qc.invalidateQueries({ queryKey: [ROOT.budgetSnapshots, budgetId] })
    },
  })
}
