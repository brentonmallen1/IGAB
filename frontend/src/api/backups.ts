import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
import { downloadAuthed } from '../utils/exportFile'
import { ROOT } from './queryKeys'

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
  /** Command written, agent (polling every ~10s) hasn't picked it up yet.
   *  `job` still describes the PREVIOUS job for that whole window. */
  queued: boolean
  job: BackupJob | null
  files: BackupFile[]
}

export interface BackupStatus {
  agent_online: boolean
  maintenance: boolean
  queued: boolean
  job: BackupJob | null
}

/** Pull a whole-application backup down to the browser.
 *
 *  Served from the mounted volume, so it works while the agent is offline —
 *  the agent makes backups, it is not needed to read one. `.age` files come
 *  down encrypted, which is what they are for. */
export function downloadBackupFile(name: string): Promise<void> {
  return downloadAuthed(`/backups/${encodeURIComponent(name)}/download`, name)
}

export function useBackups(options?: { poll?: boolean }) {
  return useQuery({
    queryKey: [ROOT.backups],
    queryFn: async () => {
      const { data } = await apiClient.get<BackupsOverview>('/backups')
      return data
    },
    // Poll fast from the moment a command is QUEUED, not just once the agent
    // reports running — gating on `running` alone left a 30s poll to notice a
    // job the agent picks up within 10s, so the new file "needed a refresh".
    refetchInterval: (query) =>
      options?.poll || query.state.data?.queued || query.state.data?.job?.state === 'running'
        ? 3_000
        : 30_000,
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
      // Seed queued=true ourselves: a refetch right now races the agent's
      // ~10s command poll and can come back with the OLD state, which both
      // hides the click's effect and drops the poller back to its slow
      // interval. The seed keeps the UI honest (and the poll fast) until a
      // real response observes the queued command.
      qc.setQueryData<BackupsOverview>([ROOT.backups], (old) =>
        old ? { ...old, queued: true } : old
      )
      qc.invalidateQueries({ queryKey: [ROOT.backups] })
      toast.success('Backup queued')
    },
    onError: (err) => {
      // The 409s here carry real answers ("already in progress", "backup
      // service is not running") that used to vanish silently.
      toast.error(apiErrorMessage(err, 'Could not start the backup'))
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
