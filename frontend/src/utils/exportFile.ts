/** Client-side report export: CSV/JSON from report aggregates, PNG from the
 * rendered chart node. Reports serialize their API aggregate (not the
 * truncated chart data), so exports carry the full result set. */

import Papa from 'papaparse'
import { toPng } from 'html-to-image'

export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function exportCsv(filename: string, rows: Record<string, unknown>[]): void {
  const csv = Papa.unparse(rows)
  downloadBlob(filename, new Blob([csv], { type: 'text/csv;charset=utf-8' }))
}

export function exportJson(filename: string, data: unknown): void {
  downloadBlob(
    filename,
    new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
  )
}

export async function exportPng(filename: string, node: HTMLElement): Promise<void> {
  // Fill with the theme background so dark themes don't export transparent
  const bg = getComputedStyle(node).getPropertyValue('--bg-primary').trim() || '#ffffff'
  const dataUrl = await toPng(node, { pixelRatio: 2, backgroundColor: bg })
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  a.click()
}

/** igab-{reportId}-{start}_{end} — window omitted for months-based reports
 * that don't pass one. */
export function exportFilename(
  reportId: string,
  ext: string,
  window?: { start: string; end: string },
): string {
  const range = window ? `-${window.start}_${window.end}` : ''
  return `igab-${reportId}${range}.${ext}`
}
