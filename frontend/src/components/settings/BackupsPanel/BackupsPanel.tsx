import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  Archive,
  Database,
  HardDriveDownload,
  History,
  Lock,
} from 'lucide-react'
import {
  fetchBackupStatus,
  useBackups,
  useRestoreBackup,
  useRunBackup,
  type BackupFile,
  type BackupJob,
} from '../../../api/backups'
import { useSettings, useUpdateSetting } from '../../../api/settings'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { useFormatters } from '../../../hooks/useFormatters'
import './BackupsPanel.css'

const KIND_LABEL: Record<BackupFile['kind'], string> = {
  db: 'Database',
  attachments: 'Attachments',
  prerestore: 'Pre-restore',
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

interface NumberSettingRowProps {
  label: string
  desc: string
  settingKey: string
  min: number
  max: number
}

function NumberSettingRow({ label, desc, settingKey, min, max }: NumberSettingRowProps) {
  const { data: appSettings } = useSettings()
  const updateSetting = useUpdateSetting()
  const saved = appSettings?.find((s) => s.key === settingKey)?.value ?? ''
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function commit() {
    if (draft === null || draft === saved) {
      setDraft(null)
      return
    }
    const n = Number(draft)
    if (!Number.isInteger(n) || n < min || n > max) {
      setError(`Must be between ${min} and ${max}`)
      return
    }
    setError(null)
    try {
      await updateSetting.mutateAsync({ key: settingKey, value: String(n) })
      setDraft(null)
    } catch {
      setError('Could not save — is the server reachable?')
    }
  }

  return (
    <div className="settings-row">
      <div>
        <div className="settings-row__label">{label}</div>
        <div className="settings-row__desc">{desc}</div>
        {error && <div className="bkp-field-error">{error}</div>}
      </div>
      <input
        type="number"
        inputMode="numeric"
        className="settings-input bkp-number-input"
        min={min}
        max={max}
        value={draft ?? saved}
        onChange={(e) => {
          setDraft(e.target.value)
          setError(null)
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        }}
      />
    </div>
  )
}

function RecipientSettingRow() {
  const { data: appSettings } = useSettings()
  const updateSetting = useUpdateSetting()
  const saved = appSettings?.find((s) => s.key === 'backup_age_recipient')?.value ?? ''
  const [draft, setDraft] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function commit() {
    if (draft === null || draft.trim() === saved) {
      setDraft(null)
      return
    }
    const value = draft.trim()
    if (value && !/^age1[0-9a-z]+$/.test(value)) {
      setError('Must be an age public key (age1…) or empty')
      return
    }
    setError(null)
    try {
      await updateSetting.mutateAsync({ key: 'backup_age_recipient', value })
      setDraft(null)
    } catch {
      setError('Could not save — is the server reachable?')
    }
  }

  return (
    <div className="settings-row bkp-recipient-row">
      <div>
        <div className="settings-row__label">Encryption key</div>
        <div className="settings-row__desc">
          Optional age public key (age1…). New backups are encrypted to it; encrypted
          backups can only be restored from the CLI with your private key — keep that
          key off this server.
        </div>
        {error && <div className="bkp-field-error">{error}</div>}
      </div>
      <input
        type="text"
        className="settings-input bkp-recipient-input"
        placeholder="age1… (empty = unencrypted)"
        spellCheck={false}
        value={draft ?? saved}
        onChange={(e) => {
          setDraft(e.target.value)
          setError(null)
        }}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
        }}
      />
    </div>
  )
}

interface RestoreModalProps {
  file: BackupFile
  onConfirm: (preBackup: boolean) => void
  onCancel: () => void
  isPending: boolean
  error: string | null
}

function RestoreModal({ file, onConfirm, onCancel, isPending, error }: RestoreModalProps) {
  const { formatDateTime } = useFormatters()
  const [preBackup, setPreBackup] = useState(true)
  const trapRef = useFocusTrap<HTMLDivElement>(onCancel)

  return (
    <div className="bkp-overlay" role="presentation">
      <div
        ref={trapRef}
        className="bkp-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="bkp-restore-title"
      >
        <div className="bkp-modal__header">
          <AlertTriangle size={18} className="bkp-modal__warn-icon" />
          <span id="bkp-restore-title">Restore from backup?</span>
        </div>
        <div className="bkp-modal__body">
          <p>
            This replaces <strong>all current data</strong> with the contents of{' '}
            <code>{file.name}</code> from {formatDateTime(file.modified_at)}.
            Anything entered since that backup will be lost.
          </p>
          <p>The app will briefly go offline and restart once the restore finishes.</p>
          <label className="bkp-modal__prebackup">
            <input
              type="checkbox"
              checked={preBackup}
              onChange={(e) => setPreBackup(e.target.checked)}
            />
            <span>
              Back up current data first (recommended) — saved as a{' '}
              <em>pre-restore</em> backup you can return to
            </span>
          </label>
          {error && <div className="bkp-field-error">{error}</div>}
        </div>
        <div className="bkp-modal__footer">
          <button className="settings-btn settings-btn--secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="settings-btn settings-btn--danger"
            onClick={() => onConfirm(preBackup)}
            disabled={isPending}
          >
            {isPending ? 'Starting…' : 'Restore'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Full-screen blocker shown from restore kickoff until the app is back. */
function RestoringOverlay() {
  const [job, setJob] = useState<BackupJob | null>(null)
  const [phase, setPhase] = useState<'restoring' | 'restarting' | 'error'>('restoring')
  // The API process exits when the agent reports a terminal state; once our
  // polls reach a fresh process (maintenance flag reset), the restore is over.
  const sawMaintenance = useRef(false)

  useEffect(() => {
    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const status = await fetchBackupStatus()
        if (cancelled) return
        setJob(status.job)
        if (status.maintenance) {
          sawMaintenance.current = true
          return
        }
        const state = status.job?.state
        if (state === 'done') {
          clearInterval(timer)
          window.location.reload()
        } else if (state === 'error') {
          clearInterval(timer)
          setPhase('error')
        }
      } catch {
        // API is restarting — keep polling until it comes back
        if (!cancelled && sawMaintenance.current) setPhase('restarting')
      }
    }, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="bkp-overlay bkp-overlay--blocking" role="alert" aria-live="assertive">
      <div className="bkp-restoring">
        {phase === 'error' ? (
          <>
            <AlertTriangle size={28} className="bkp-restoring__error-icon" />
            <div className="bkp-restoring__title">Restore failed</div>
            <p className="bkp-restoring__detail">
              {job?.detail ?? 'See the backup service container logs for details.'}
            </p>
            <button
              className="settings-btn settings-btn--primary"
              onClick={() => window.location.reload()}
            >
              Reload app
            </button>
          </>
        ) : (
          <>
            <div className="bkp-restoring__spinner" aria-hidden="true" />
            <div className="bkp-restoring__title">
              {phase === 'restarting' ? 'Restarting the app…' : 'Restoring from backup…'}
            </div>
            <p className="bkp-restoring__detail">
              {phase === 'restarting'
                ? 'Almost there — the page will reload automatically.'
                : (job?.detail ?? 'Starting…')}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

export function BackupsPanel() {
  const { formatDateTime } = useFormatters()
  const { data, isLoading } = useBackups()
  const runBackup = useRunBackup()
  const restoreBackup = useRestoreBackup()
  const [restoreTarget, setRestoreTarget] = useState<BackupFile | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState(false)

  const agentOnline = data?.agent_online ?? false
  const job = data?.job ?? null
  const jobRunning = job?.state === 'running' && agentOnline
  // Between the click and the agent's next command poll (up to ~10s), the
  // command file is the only evidence anything happened — `job` still
  // describes the previous run for that whole window.
  const queued = (data?.queued ?? false) && agentOnline
  const busy = queued || jobRunning || runBackup.isPending
  const files = data?.files ?? []

  async function startRestore(preBackup: boolean) {
    if (!restoreTarget) return
    setRestoreError(null)
    try {
      await restoreBackup.mutateAsync({ file: restoreTarget.name, pre_backup: preBackup })
      setRestoreTarget(null)
      setRestoring(true)
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setRestoreError(detail ?? 'Could not start the restore')
    }
  }

  return (
    <div className="bkp-panel">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">
            Backup service{' '}
            <span
              className={`bkp-status-pill ${
                agentOnline ? 'bkp-status-pill--online' : 'bkp-status-pill--offline'
              }`}
            >
              {agentOnline ? 'online' : 'offline'}
            </span>
          </div>
          <div className="settings-row__desc">
            {agentOnline
              ? 'Automatic pg_dump + attachment archives on a schedule, with retention pruning. Settings below apply within seconds — no restart needed.'
              : 'The backup service is not running — check the container logs. Multi-container: it starts with the production compose profile (docker compose up -d db-backup). AIO: it runs inside the main container; make sure you are on the latest image.'}
          </div>
        </div>
        <button
          className="settings-btn settings-btn--primary"
          onClick={() => runBackup.mutate()}
          disabled={!agentOnline || busy}
        >
          <HardDriveDownload size={14} />
          {jobRunning && job?.action === 'backup'
            ? 'Backing up…'
            : queued
              ? 'Queued…'
              : 'Back up now'}
        </button>
      </div>

      {/* While queued/running, the previous job's result reads as if THIS
          click already finished — suppress it until the new job reports. */}
      {job && !queued && !jobRunning && job.state !== 'running' && job.action === 'backup' && (
        <div
          className={`bkp-job-note ${job.state === 'error' ? 'bkp-job-note--error' : ''}`}
        >
          Last manual backup: {job.state === 'done' ? 'completed' : `failed — ${job.detail}`}
          {job.finished_at ? ` (${formatDateTime(job.finished_at)})` : ''}
        </div>
      )}

      <NumberSettingRow
        label="Backup interval"
        desc="Hours between automatic backups (1–168)"
        settingKey="backup_interval_hours"
        min={1}
        max={168}
      />
      <NumberSettingRow
        label="Retention"
        desc="Delete backups older than this many days (1–365)"
        settingKey="backup_keep_days"
        min={1}
        max={365}
      />
      <NumberSettingRow
        label="Minimum kept"
        desc="Always keep at least this many recent backups of each kind, even past retention (1–100)"
        settingKey="backup_keep_min"
        min={1}
        max={100}
      />
      <RecipientSettingRow />

      <div className="bkp-files">
        <div className="bkp-files__title">Existing backups</div>
        {isLoading ? (
          <div className="bkp-files__empty">Loading…</div>
        ) : files.length === 0 ? (
          <div className="bkp-files__empty">
            No backups yet{agentOnline ? ' — one will be created on the next cycle.' : '.'}
          </div>
        ) : (
          <table className="bkp-table surface surface--sunken">
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Kind</th>
                <th scope="col">Size</th>
                <th scope="col">Created</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => {
                const restorable = f.kind !== 'attachments' && !f.encrypted
                const hint = f.encrypted
                  ? 'Encrypted — restore from the CLI with your age private key: just restore ' +
                    f.name
                  : f.kind === 'attachments'
                    ? 'Attachment archives are restored from the CLI (see README → Backups)'
                    : undefined
                return (
                  <tr key={f.name}>
                    <td className="bkp-table__name">
                      <span className="bkp-table__name-inner">
                        {f.kind === 'attachments' ? (
                          <Archive size={13} aria-hidden="true" />
                        ) : f.kind === 'prerestore' ? (
                          <History size={13} aria-hidden="true" />
                        ) : (
                          <Database size={13} aria-hidden="true" />
                        )}
                        {f.name}
                        {f.encrypted && (
                          <Lock size={12} className="bkp-table__lock" aria-label="Encrypted" />
                        )}
                      </span>
                    </td>
                    <td>{KIND_LABEL[f.kind]}</td>
                    <td>{formatBytes(f.size_bytes)}</td>
                    <td>{formatDateTime(f.modified_at)}</td>
                    <td className="bkp-table__action">
                      {restorable ? (
                        <button
                          className="settings-btn settings-btn--secondary bkp-restore-btn"
                          onClick={() => {
                            setRestoreError(null)
                            setRestoreTarget(f)
                          }}
                          disabled={!agentOnline || jobRunning}
                        >
                          Restore
                        </button>
                      ) : (
                        <span className="bkp-table__cli-hint" title={hint}>
                          CLI
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {restoreTarget && (
        <RestoreModal
          file={restoreTarget}
          onConfirm={startRestore}
          onCancel={() => setRestoreTarget(null)}
          isPending={restoreBackup.isPending}
          error={restoreError}
        />
      )}
      {restoring && <RestoringOverlay />}
    </div>
  )
}
