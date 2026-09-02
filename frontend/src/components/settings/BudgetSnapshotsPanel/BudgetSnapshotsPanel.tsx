/**
 * One budget, in one file.
 *
 * The panel above this one backs up the whole installation and is admin-only.
 * This is the per-budget half: download a copy, keep copies on the server,
 * duplicate a budget from a file, or put a budget back the way it was.
 *
 * Deliberately wearing the same clothes as BackupsPanel — same table, same
 * modal shape — because it is the same job. Two visual languages for "a list
 * of backup files with actions" would be a duplicate that drifts.
 *
 * A file is inspected before anything can be done with it: the server reads
 * its manifest and says whether it can be read, without writing a row. That
 * is what makes "check before you restore" a real option, and it is why the
 * two actions only appear once a file has been read.
 */

import { useRef, useState } from 'react'
import {
  AlertTriangle,
  Database,
  Download,
  FileSpreadsheet,
  HardDriveDownload,
  Trash2,
  Upload,
} from 'lucide-react'
import toast from 'react-hot-toast'
import {
  downloadBudgetExport,
  downloadKeptSnapshot,
  downloadSnapshotNow,
  inspectSnapshot,
  tooLargeMessage,
  useBudgetSnapshots,
  useCreateBudgetSnapshot,
  useDeleteBudgetSnapshot,
  useImportSnapshot,
  useRestoreSnapshot,
  type SnapshotInspection,
} from '../../../api/budgetSnapshots'
import { apiErrorMessage } from '../../../api/client'
import { useFocusTrap } from '../../../hooks/useFocusTrap'
import { useFormatters } from '../../../hooks/useFormatters'
import '../BackupsPanel/BackupsPanel.css'
import './BudgetSnapshotsPanel.css'

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function totalRows(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, n) => sum + n, 0)
}

interface RestoreModalProps {
  budgetName: string
  inspection: SnapshotInspection
  onConfirm: (confirmName: string, preSnapshot: boolean) => void
  onCancel: () => void
  isPending: boolean
  error: string | null
}

/** Typing the budget's name, not ticking a box: this replaces everything in
 *  the budget, and the confirmation should cost as much as the action. */
function RestoreModal({
  budgetName,
  inspection,
  onConfirm,
  onCancel,
  isPending,
  error,
}: RestoreModalProps) {
  const ref = useFocusTrap<HTMLDivElement>(onCancel)
  const [typed, setTyped] = useState('')
  const [preSnapshot, setPreSnapshot] = useState(true)
  const matches = typed.trim() === budgetName

  return (
    <div className="bkp-overlay" role="presentation">
      <div
        ref={ref}
        className="bkp-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Restore budget"
      >
        <div className="bkp-modal__header">
          <AlertTriangle size={18} className="bkp-modal__warn-icon" />
          <span>Restore “{budgetName}”</span>
        </div>
        <div className="bkp-modal__body">
          <p>
            Everything in this budget is replaced with the {totalRows(inspection.row_counts)} rows
            in this file, taken {inspection.exported_at.slice(0, 10)}. The budget keeps its name,
            who it is shared with, and its place in your list.
          </p>
          {inspection.attachments_omitted > 0 && (
            <p className="snap-note">
              Receipts are not stored in the file. Those still attached to transactions the snapshot
              contains are kept; any attached to newer transactions are let go.
            </p>
          )}
          <label className="bkp-modal__prebackup">
            <input
              type="checkbox"
              checked={preSnapshot}
              onChange={(e) => setPreSnapshot(e.target.checked)}
            />
            Save a snapshot of the current state first
          </label>
          <label className="snap-confirm">
            Type <strong>{budgetName}</strong> to confirm
            <input
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              aria-label="Budget name"
            />
          </label>
          {error && <div className="bkp-field-error">{error}</div>}
        </div>
        <div className="bkp-modal__footer">
          <button className="settings-btn settings-btn--secondary" onClick={onCancel}>
            Cancel
          </button>
          <button
            className="settings-btn settings-btn--danger"
            disabled={!matches || isPending}
            onClick={() => onConfirm(typed, preSnapshot)}
          >
            {isPending ? 'Restoring…' : 'Replace this budget'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface Props {
  budgetId: string
  budgetName: string
}

export function BudgetSnapshotsPanel({ budgetId, budgetName }: Props) {
  const { formatDateTime } = useFormatters()
  const { data: files, isLoading } = useBudgetSnapshots(budgetId)
  const create = useCreateBudgetSnapshot(budgetId)
  const remove = useDeleteBudgetSnapshot(budgetId)
  const importSnapshot = useImportSnapshot()
  const restore = useRestoreSnapshot(budgetId)

  const fileInput = useRef<HTMLInputElement>(null)
  const [chosen, setChosen] = useState<File | null>(null)
  const [inspection, setInspection] = useState<SnapshotInspection | null>(null)
  const [inspecting, setInspecting] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [restoreOpen, setRestoreOpen] = useState(false)
  const [restoreError, setRestoreError] = useState<string | null>(null)

  function clearFile() {
    setChosen(null)
    setInspection(null)
    setFileError(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  async function chooseFile(file: File | undefined) {
    if (!file) return
    setInspection(null)
    // Checked here so a person gets a sentence: over the limit, nginx answers
    // a bare 413 that never reaches the app.
    const tooLarge = tooLargeMessage(file.size)
    if (tooLarge) {
      setChosen(null)
      setFileError(tooLarge)
      return
    }
    setChosen(file)
    setFileError(null)
    setInspecting(true)
    try {
      setInspection(await inspectSnapshot(file))
    } catch (err) {
      setFileError(apiErrorMessage(err, 'That file could not be read'))
      setChosen(null)
    } finally {
      setInspecting(false)
    }
  }

  async function doRestore(confirmName: string, preSnapshot: boolean) {
    if (!chosen) return
    setRestoreError(null)
    try {
      const result = await restore.mutateAsync({ file: chosen, confirmName, preSnapshot })
      setRestoreOpen(false)
      clearFile()
      toast.success(
        result.attachments_dropped > 0
          ? `Restored. ${result.attachments_dropped} receipt(s) had no transaction to return to.`
          : 'Restored'
      )
    } catch (err) {
      setRestoreError(apiErrorMessage(err, 'The restore did not run'))
    }
  }

  const kept = files ?? []

  return (
    <div className="bkp-panel">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Snapshot this budget</div>
          <div className="settings-row__desc">
            One file holding this budget alone — accounts, categories, transactions, targets and
            plans. Receipts are not included.
          </div>
        </div>
        <div className="snap-actions">
          <button
            className="settings-btn settings-btn--secondary"
            onClick={() =>
              downloadSnapshotNow(budgetId, budgetName).catch(() => toast.error('Export failed.'))
            }
          >
            <Download size={14} aria-hidden="true" /> IGAB export
          </button>
          <button
            className="settings-btn"
            onClick={() => create.mutate()}
            disabled={create.isPending}
          >
            <HardDriveDownload size={14} aria-hidden="true" />
            {create.isPending ? 'Saving…' : 'Keep on server'}
          </button>
        </div>
      </div>

      <div className="settings-row">
        <div>
          <div className="settings-row__label">Export it to read elsewhere</div>
          <div className="settings-row__desc">
            A spreadsheet-friendly file in YNAB&rsquo;s shape — it opens in Excel or Numbers, and
            IGAB reads it back. It cannot carry everything a snapshot does, and the file lists what
            it left behind.
          </div>
        </div>
        <div className="snap-actions">
          <button
            className="settings-btn settings-btn--secondary"
            onClick={() =>
              downloadBudgetExport(budgetId, budgetName).catch(() => toast.error('Export failed.'))
            }
          >
            <FileSpreadsheet size={14} aria-hidden="true" /> YNAB export
          </button>
        </div>
      </div>

      <div className="bkp-files">
        <div className="bkp-files__title">Snapshots of this budget</div>
        {isLoading ? (
          <div className="bkp-files__empty">Loading…</div>
        ) : kept.length === 0 ? (
          <div className="bkp-files__empty">
            None kept on the server yet. “Keep on server” saves one beside your other backups.
          </div>
        ) : (
          <table className="bkp-table surface surface--sunken">
            <thead>
              <tr>
                <th scope="col">File</th>
                <th scope="col">Size</th>
                <th scope="col">Created</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {kept.map((f) => (
                <tr key={f.name}>
                  <td className="bkp-table__name">
                    <span className="bkp-table__name-inner">
                      <Database size={13} aria-hidden="true" />
                      {f.name}
                    </span>
                  </td>
                  <td>{formatBytes(f.size_bytes)}</td>
                  <td>{formatDateTime(f.modified_at)}</td>
                  <td className="bkp-table__action snap-row-actions">
                    <button
                      className="settings-btn settings-btn--secondary"
                      onClick={() =>
                        downloadKeptSnapshot(budgetId, f.name).catch(() =>
                          toast.error('Download failed.')
                        )
                      }
                      aria-label={`Download ${f.name}`}
                    >
                      <Download size={13} aria-hidden="true" />
                    </button>
                    <button
                      className="settings-btn settings-btn--secondary"
                      onClick={() => remove.mutate(f.name)}
                      aria-label={`Delete ${f.name}`}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="settings-row snap-upload">
        <div>
          <div className="settings-row__label">Load a snapshot file</div>
          <div className="settings-row__desc">
            The file is read and checked before anything happens to your data. Then you choose what
            to do with it.
          </div>
        </div>
        <label className="settings-btn settings-btn--secondary snap-file-btn">
          <Upload size={14} aria-hidden="true" />
          {chosen ? 'Choose another' : 'Choose a file'}
          <input
            ref={fileInput}
            type="file"
            accept=".zip,.igab.zip,application/zip"
            onChange={(e) => chooseFile(e.target.files?.[0])}
            hidden
          />
        </label>
      </div>

      {fileError && <div className="bkp-field-error">{fileError}</div>}
      {inspecting && <div className="bkp-files__empty">Reading the file…</div>}

      {inspection && (
        <div className="snap-inspection surface surface--sunken">
          <div className="snap-inspection__head">
            <strong>{inspection.budget_name}</strong>
            <span className="snap-inspection__meta">
              exported {inspection.exported_at.slice(0, 10)} · {totalRows(inspection.row_counts)}{' '}
              rows · IGAB {inspection.app_version}
            </span>
          </div>
          {!inspection.ok && (
            <ul className="snap-inspection__refusals">
              {inspection.refusals.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {inspection.warnings.length > 0 && (
            <ul className="snap-inspection__warnings">
              {inspection.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          {inspection.attachments_omitted > 0 && (
            <p className="snap-note">
              {inspection.attachments_omitted} receipt(s) are not carried in this file.
            </p>
          )}
          {inspection.ok && (
            <div className="snap-actions">
              <button
                className="settings-btn"
                disabled={importSnapshot.isPending || !chosen}
                onClick={() => {
                  if (!chosen) return
                  importSnapshot.mutate({ file: chosen }, { onSuccess: clearFile })
                }}
              >
                {importSnapshot.isPending ? 'Importing…' : 'Import as a new budget'}
              </button>
              <button
                className="settings-btn settings-btn--danger"
                onClick={() => {
                  setRestoreError(null)
                  setRestoreOpen(true)
                }}
              >
                Replace “{budgetName}”
              </button>
            </div>
          )}
        </div>
      )}

      {restoreOpen && inspection && (
        <RestoreModal
          budgetName={budgetName}
          inspection={inspection}
          onConfirm={doRestore}
          onCancel={() => setRestoreOpen(false)}
          isPending={restore.isPending}
          error={restoreError}
        />
      )}
    </div>
  )
}
