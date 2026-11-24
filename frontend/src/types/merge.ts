/**
 * Merging two transactions into one: the picks a person makes and the result
 * the server says they produce. Split out of `types/index.ts` (which
 * re-exports this) to keep it inside the file-length budget.
 *
 * Nothing here is decided on the client. Which fields are a choice, where
 * each value comes from and what the merged row reads are all
 * `merge_bookkeeping` in backend/src/igab/domain/merging.py, served by
 * POST /{budget}/transactions/merge/preview.
 */

/** Which row each field is kept from — a transaction id. Absent leaves the
 *  server's default. `memo` may be `'both'`: two different memos, joined. */
export interface MergeKeep {
  date?: string
  payee?: string
  category?: string
  memo?: string
}

export type MergeField = keyof MergeKeep

/** One field of the result: the row its value comes from (null when neither
 *  row has one; `'both'` for two memos joined), and whether the other row's
 *  value could be picked instead. */
export interface MergeChoice {
  source: string | null
  choosable: boolean
}

export interface MergePreviewLine {
  amount: number
  category_id: string | null
  memo: string | null
}

/** The transaction a merge would leave behind. */
export interface MergePreview {
  survivor_id: string
  deleted_id: string
  date: string
  amount: number
  /** The kept row's own amount, when the bank's posted amount replaces it. */
  replaced_amount: number | null
  payee_id: string | null
  category_id: string | null
  memo: string | null
  cleared: string
  is_split: boolean
  /** The split lines the result carries; empty when it is not a split. */
  lines: MergePreviewLine[]
  has_bank_record: boolean
  import_description: string | null
  bank_posted_date: string | null
  /** What becomes of a transfer either row is part of, if any. */
  transfer: 'kept' | 'taken_over' | 'other_side_merged' | null
  choices: Record<MergeField, MergeChoice>
}
