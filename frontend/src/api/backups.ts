import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface BackupFile {
  name: string
  kind: 'db' | 'attachments' | 'prerestore'
  size_bytes: number
  modified_at: string
  encrypted: boolean
}

export interface BackupJob {
  id: string | null
  action: string | null
  state: 'running' | 'done' | 'error' | null
  detail: string | null
  started_at: string | null
  finished_at: string | null
}

export interface BackupsOverview {
  agent_online: boolean
  agent_last_seen: string | null
  maintenance: boolean
  job: BackupJob | null
  files: BackupFile[]
}

export interface BackupStatus {
  agent_online: boolean
  maintenance: boolean
  job: BackupJob | null
}

export function useBackups(options?: { poll?: boolean }) {
  return useQuery({
    queryKey: ['backups'],
    queryFn: async () => {
      const { data } = await apiClient.get<BackupsOverview>('/backups')
      return data
    },
    // Poll faster while a job is running so the file list and job state stay live
    refetchInterval: (query) =>
      options?.poll || query.state.data?.job?.state === 'running' ? 3_000 : 30_000,
  })
}

/** Job progress via the DB-free status endpoint — keeps working mid-restore. */
export async function fetchBackupStatus(): Promise<BackupStatus> {
  const { data } = await apiClient.get<BackupStatus>('/backups/status')
  return data
}

export function useRunBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient.post<{ job_id: string }>('/backups/run').then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['backups'] })
    },
  })
}

export function useRestoreBackup() {
  return useMutation({
    mutationFn: (body: { file: string; pre_backup: boolean }) =>
      apiClient
        .post<{ job_id: string }>('/backups/restore', { ...body, confirm: true })
        .then((r) => r.data),
  })
}
