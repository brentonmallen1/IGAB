import { useEffect, useRef, useState } from 'react'
import { Download } from 'lucide-react'
import toast from 'react-hot-toast'
import { exportCsv, exportFilename, exportJson, exportPng } from '../../../utils/exportFile'
import './ReportExportButton.css'

interface Props {
  reportId: string
  /** Rows for CSV/JSON, built lazily on click from the report's API aggregate */
  getRows: () => Record<string, unknown>[]
  /** Node captured for PNG — the chart area, not the controls */
  captureRef: React.RefObject<HTMLDivElement | null>
  window?: { start: string; end: string }
}

export function ReportExportButton({ reportId, getRows, captureRef, window }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  async function handle(format: 'csv' | 'json' | 'png') {
    setOpen(false)
    try {
      if (format === 'png') {
        if (!captureRef.current) return
        await exportPng(exportFilename(reportId, 'png', window), captureRef.current)
        return
      }
      const rows = getRows()
      if (rows.length === 0) {
        toast.error('Nothing to export for this period.')
        return
      }
      if (format === 'csv') exportCsv(exportFilename(reportId, 'csv', window), rows)
      else exportJson(exportFilename(reportId, 'json', window), rows)
    } catch {
      toast.error('Export failed.')
    }
  }

  return (
    <div className="report-export-btn" ref={rootRef}>
      <button
        className="report-btn report-export-btn__trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        type="button"
      >
        <Download size={14} />
        Export
      </button>
      {open && (
        <div className="report-export-btn__menu" role="menu">
          <button role="menuitem" onClick={() => handle('csv')} type="button">
            CSV
          </button>
          <button role="menuitem" onClick={() => handle('json')} type="button">
            JSON
          </button>
          <button role="menuitem" onClick={() => handle('png')} type="button">
            PNG
          </button>
        </div>
      )}
    </div>
  )
}
