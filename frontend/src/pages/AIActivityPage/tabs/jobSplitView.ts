import type { AIJob } from '../../../api/aiJobs'
import type { Transaction } from '../../../types'
import type { NamedCategory } from '../../../utils/categoryLabels'
import { parseApiDecimal } from '../../../utils/money'

export interface JobSplitLine {
  label: string
  amount: number
}

/**
 * The split a scan's card shows, if any:
 *
 * - `filed` — the row is split. Its lines as they stand now, served
 *   (`useSplitLinesFor`), not the model's read: a line edited since the scan
 *   reads as edited.
 * - `suggested` — the model itemised the receipt but the row is filed in one
 *   category: the read landed on a row that already had one, or a line's
 *   category stopped resolving (`receipt_fields.may_file_split`). Its labels
 *   are the model's, as read.
 *
 * Null with no row to describe, no split either way, or a split row whose
 * lines have not arrived — a card does not draw a split it cannot itemise.
 */
export type JobSplitView = { kind: 'filed' | 'suggested'; lines: JobSplitLine[] }

export function jobSplitView(
  job: AIJob,
  served: readonly Transaction[] | undefined,
  labels: ReadonlyMap<string, NamedCategory>
): JobSplitView | null {
  if (!job.transaction_id || !job.transaction_account_id) return null
  if (job.transaction_is_split) {
    if (!served || served.length === 0) return null
    return {
      kind: 'filed',
      lines: served.map((line) => ({
        label: line.category_id
          ? (labels.get(line.category_id)?.name ?? 'Unknown category')
          : 'Uncategorized',
        amount: line.amount,
      })),
    }
  }
  const suggested = job.result?.suggested_split
  if (!suggested || suggested.length < 2) return null
  return {
    kind: 'suggested',
    lines: suggested.map((line) => ({
      label: line.category,
      amount: parseApiDecimal(line.amount),
    })),
  }
}

/** The split rows among a list's jobs: the parents one request asks lines for. */
export function splitParentIds(jobs: readonly AIJob[]): string[] {
  return jobs
    .filter((job) => job.transaction_is_split && job.transaction_id)
    .map((job) => job.transaction_id!)
}
