/**
 * What a CSV preview says the import will do, in words.
 *
 * The outcomes are the server's (services/csv_import.py runs the bank-match
 * ladder over every line); this only composes them into words. Shared by the
 * account's import dialog and the Import page, which used to word the same
 * result twice. Pure, so every branch is a one-line test.
 */
import type { CsvImportResult, CsvPreview, CsvPreviewRow } from '../api/imports'

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** Rows the import will write: new lines and lines it queues for review. */
export function rowsToWrite(preview: CsvPreview): number {
  return preview.new_rows + preview.review_rows
}

/** Whether pressing Import changes anything. A file whose every line is
 *  already here can still clear the rows it matched — that is work too. */
export function hasWork(preview: CsvPreview): boolean {
  return rowsToWrite(preview) + preview.confirmed_rows > 0
}

export function primaryLabel(preview: CsvPreview | null): string {
  if (!preview) return 'Import'
  const writing = rowsToWrite(preview)
  if (writing > 0) return `Import ${plural(writing, 'transaction')}`
  if (preview.confirmed_rows > 0) return `Clear ${plural(preview.confirmed_rows, 'transaction')}`
  return 'Import'
}

export type RowTag = { label: string; tone: 'here' | 'clear' | 'review' }

/** The tag beside a sample line, or null for a plain new row. */
export function rowTag(row: CsvPreviewRow): RowTag | null {
  switch (row.outcome) {
    case 'already_imported':
      return { label: 'already here', tone: 'here' }
    case 'matched':
      return row.confirms
        ? { label: 'will clear', tone: 'clear' }
        : { label: 'already here', tone: 'here' }
    case 'review':
      return { label: 'to review', tone: 'review' }
    default:
      return null
  }
}

/** A line nothing new is written for — dimmed in the sample. */
export function isAlreadyHere(row: CsvPreviewRow): boolean {
  return row.outcome === 'already_imported' || row.outcome === 'matched'
}

/** What an import did, in one line. */
export function resultMessage(result: CsvImportResult): string {
  const parts: string[] = []
  if (result.imported > 0) parts.push(`Imported ${plural(result.imported, 'transaction')}`)
  if (result.confirmed > 0) parts.push(`cleared ${result.confirmed} already here`)
  if (result.review > 0) parts.push(`${result.review} to review`)
  if (parts.length === 0) return 'Nothing new to import — every row was already here'
  const text = parts.join(' · ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}
