import { useState } from 'react'
import toast from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'
import { Upload } from 'lucide-react'
import { Dialog } from '../../common/Dialog/Dialog'
import { useFormatters } from '../../../hooks/useFormatters'
import {
  previewCsv,
  importCsv,
  type CsvField,
  type CsvMapping,
  type CsvPreview,
} from '../../../api/imports'
import { invalidateAfterImport } from '../../../api/invalidateAfterImport'
import { useUndoToast } from '../../../utils/toastUndo'
import { applicableMapping, rememberMapping } from './csvMappingMemory'
import './CsvImportDialog.css'

/** The fields a column can be mapped to, in the order they are asked about. */
const FIELDS: { key: CsvField; label: string; hint?: string }[] = [
  { key: 'date', label: 'Date' },
  { key: 'payee', label: 'Payee' },
  { key: 'amount', label: 'Amount', hint: 'One column carrying its own sign' },
  { key: 'debit', label: 'Debit', hint: 'Or two columns: money out…' },
  { key: 'credit', label: 'Credit', hint: '…and money in' },
  { key: 'memo', label: 'Memo' },
  { key: 'category', label: 'Category', hint: 'Matched to envelopes you already have' },
]

interface Props {
  budgetId: string
  accountId: string
  accountName: string
  onClose: () => void
}

/**
 * Import this account's own export from its bank.
 *
 * Two phases, because the interesting question is not "did it work" but "what
 * is about to happen": a bank export overlaps the previous one almost every
 * time, and the count of rows already imported is the thing worth seeing
 * before anything lands rather than afterwards in a number nobody can check.
 */
export function CsvImportDialog({ budgetId, accountId, accountName, onClose }: Props) {
  const { formatMoney, formatDate } = useFormatters()
  const queryClient = useQueryClient()
  const notify = useUndoToast()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<CsvPreview | null>(null)
  const [mapping, setMapping] = useState<CsvMapping>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function detailOf(err: unknown, fallback: string) {
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    return typeof detail === 'string' ? detail : fallback
  }

  async function look(chosen: File, withMapping?: CsvMapping) {
    setBusy(true)
    setError(null)
    try {
      const result = await previewCsv(budgetId, accountId, chosen, withMapping)
      setPreview(result)
      setMapping(result.mapping)
      setFile(chosen)
    } catch (err) {
      setError(detailOf(err, 'Could not read that file'))
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  async function onPick(chosen: File) {
    // Headers are unknown until the first read, so the remembered mapping is
    // applied on the second: ask the server what the file looks like, then
    // re-ask with the columns this account used last time.
    const first = await previewCsv(budgetId, accountId, chosen).catch(() => null)
    const remembered = first ? applicableMapping(accountId, first.headers) : undefined
    if (remembered) return look(chosen, remembered)
    if (first) {
      setPreview(first)
      setMapping(first.mapping)
      setFile(chosen)
      return
    }
    return look(chosen)
  }

  function setColumn(field: CsvField, column: string) {
    const next = { ...mapping }
    if (column) next[field] = column
    else delete next[field]
    setMapping(next)
    if (file) void look(file, next)
  }

  async function commit() {
    // Enabled before there is anything to import, like every dialog's
    // primary, and says why on press rather than sitting greyed out.
    if (!file || !preview) return setError('Choose a CSV file to import')
    if (preview.new_rows === 0) {
      return setError(`Every row is already in ${accountName} — nothing to import`)
    }
    setError(null)
    setBusy(true)
    try {
      const result = await importCsv(budgetId, accountId, file, mapping)
      rememberMapping(accountId, mapping)
      invalidateAfterImport(queryClient, budgetId)
      if (result.batch_id && result.imported > 0) {
        notify(`Imported ${result.imported} transaction${result.imported === 1 ? '' : 's'}`, {
          batch: result.batch_id,
        })
      } else {
        toast.success('Nothing new to import — every row was already here')
      }
      onClose()
    } catch (err) {
      setError(detailOf(err, 'Import failed'))
    } finally {
      setBusy(false)
    }
  }

  const nothingNew = preview !== null && preview.new_rows === 0

  return (
    <Dialog
      title={`Import transactions — ${accountName}`}
      onClose={onClose}
      historyKey="csv-import"
      width="lg"
      footer={
        <div className="dialog-actions">
          {error && (
            <span className="dialog-form__error" role="alert">
              {error}
            </span>
          )}
          <div className="dialog-actions__end">
            <button type="button" className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn--primary"
              disabled={busy}
              onClick={commit}
            >
              {busy
                ? 'Working…'
                : preview
                  ? `Import ${preview.new_rows} transaction${preview.new_rows === 1 ? '' : 's'}`
                  : 'Import'}
            </button>
          </div>
        </div>
      }
    >
      {!preview && (
        <label className="csv-import__drop">
          <Upload size={20} aria-hidden />
          <span>Choose the CSV your bank exported for this account</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const chosen = e.target.files?.[0]
              if (chosen) void onPick(chosen)
            }}
          />
        </label>
      )}

      {preview && (
        <>
          <div className="csv-import__counts">
            <span>
              <strong>{preview.total_rows}</strong> rows
            </span>
            <span>
              <strong>{preview.new_rows}</strong> new
            </span>
            {/* The headline, not a footnote: re-exporting from a bank
                overlaps the previous export almost every time. */}
            <span className={preview.duplicate_rows ? 'csv-import__dupes' : undefined}>
              <strong>{preview.duplicate_rows}</strong> already imported
            </span>
            {preview.skipped.length > 0 && (
              <span className="csv-import__skipped-count">
                <strong>{preview.skipped.length}</strong> skipped
              </span>
            )}
          </div>

          {/* The grid is this dialog's; each cell is the shared field. */}
          <div className="dialog-form csv-import__mapping-form">
            <div className="csv-import__mapping">
              {FIELDS.map((f) => (
                <label key={f.key} className="dialog-form__field">
                  <span>{f.label}</span>
                  {f.hint && <small className="dialog-form__hint">{f.hint}</small>}
                  <select
                    value={mapping[f.key] ?? ''}
                    onChange={(e) => setColumn(f.key, e.target.value)}
                  >
                    <option value="">—</option>
                    {preview.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </div>

          {preview.date_format && (
            <p className="csv-import__note">
              Dates read as <code>{preview.date_format}</code> — check the first row below if that
              could be day-first or month-first.
            </p>
          )}

          {preview.skipped.length > 0 && (
            <details className="csv-import__skipped">
              <summary>{preview.skipped.length} rows will be skipped</summary>
              <ul>
                {preview.skipped.slice(0, 20).map((s) => (
                  <li key={s.line}>
                    Row {s.line}: {s.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <table className="csv-import__sample">
            <caption className="sr-only">The first rows, as they were understood</caption>
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Payee</th>
                <th scope="col" style={{ textAlign: 'right' }}>
                  Amount
                </th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {preview.sample.map((row) => (
                <tr key={row.line} className={row.duplicate ? 'csv-import__row--dupe' : undefined}>
                  <td>{formatDate(row.date)}</td>
                  <td>{row.payee || <span className="csv-import__muted">No payee</span>}</td>
                  <td style={{ textAlign: 'right' }}>{formatMoney(row.amount)}</td>
                  <td>{row.duplicate && <span className="csv-import__tag">already here</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {nothingNew && (
            <p className="csv-import__note">
              Every row in this file is already in {accountName}. Nothing to import.
            </p>
          )}
        </>
      )}
    </Dialog>
  )
}
