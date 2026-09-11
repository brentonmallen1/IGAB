import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

export interface CsvImportResult {
  imported: number
  skipped: number
  errors: string[]
  /** Change-log batch id for undo (null if nothing was imported). */
  batch_id: string | null
}

/** Whether the export's own numbers agree with each other.
 *
 *  Parity holds IGAB's recomputed Available against the Available column
 *  YNAB shipped, which only means something if the file hangs together.
 *  `carryover` checks each category's months against YNAB's own running
 *  balance; `activity` checks each Plan Activity cell against the register
 *  rows shipped beside it. */
export interface YnabExportConsistency {
  self_consistent: boolean
  carryover_rows_checked: number
  carryover_rows_violating: number
  activity_cells_checked: number
  activity_cells_disagreeing: number
}

/** How the imported budget compares with the export's own figures. */
export interface YnabParity {
  month: string
  /** What YNAB's numbers say Ready to Assign is. */
  ynab_ready_to_assign: string
  /** That figure, adjusted by the one difference IGAB makes on purpose:
   *  card debt YNAB parks unfunded (`uncovered_card_debt`). */
  expected_ready_to_assign: string
  igab_ready_to_assign: string
  uncovered_card_debt: string
  /** Uncategorized rows on budget accounts: out of Ready to Assign here
   *  until filed, out of YNAB's plan entirely. */
  uncategorized_net: string
  /** expected == igab AND every envelope equals YNAB's Available. */
  matches: boolean
  categories_compared: number
  /** Envelopes that differ by something other than their pending rows. */
  categories_differing: number
  /** Envelopes that differ by exactly their uncleared rows this month —
   *  YNAB counts an imported row only once it is approved. */
  categories_pending: number
  /** Envelopes YNAB priced that no IGAB category answered to. Not compared;
   *  reported so `categories_compared` is explainable. */
  categories_unmatched: number
  /** Whether the export's own numbers agree with each other. When they do
   *  not, `categories_differing` measures the file, not the import. */
  consistency: YnabExportConsistency
  /** Card set-asides held against the per-card Credit Card Payments reserve
   *  YNAB shipped. A differing card is an envelope that detached from its
   *  ledger over the imported history — checked at import because that is
   *  when the drift is largest and the user has no baseline to notice it. */
  cards_compared: number
  cards_differing: number
  card_differences: {
    name: string
    igab: string
    ynab: string
  }[]
  /** Per card, the first month the set-aside detached from YNAB's reserve —
   *  every month of the plan is compared, not just the viewed one. On a long
   *  import "which month" is the actionable half. Empty when every card
   *  agrees everywhere. */
  card_history: {
    name: string
    first_month: string
    igab: string
    ynab: string
    months_compared: number
    months_differing: number
  }[]
  top_differences: {
    name: string
    igab: string
    ynab: string
    /** Uncleared rows this month. When it equals the gap, the difference is
     *  YNAB not having approved an import yet rather than a disagreement. */
    pending: string
  }[]
}

/** One tag the import applied, and the name that made it. */
export interface YnabTaggedCategory {
  category_id: string
  system_key: string
  /** The category's own name or its group's — whichever triggered the hint. */
  matched_on: string
}

/** A register row dated after the import that became an upcoming
 *  transaction instead of a posted one (server: YNABHeldOutFuture). */
export interface YnabHeldOutFuture {
  scheduled_transaction_id: string
  account_name: string
  date: string
  payee: string
  amount: string
  category_name: string | null
  is_transfer: boolean
  /** Non-empty for a split: scheduled uncategorized, legs written into the
   *  memo, so the review can say it still needs a category. */
  split_legs: string[]
}

export interface YnabImportResult {
  accounts: number
  category_groups: number
  categories: number
  transactions: number
  skipped: number
  assignments: number
  /** Accounts the user chose to leave out (closed/archived YNAB accounts). */
  accounts_skipped: number
  /** Imported in full, then closed at the user's request — every transaction
   *  arrived, only the account is hidden from pickers and report filters. */
  accounts_closed: number
  /** Rows belonging to those accounts — distinct from `skipped` (dedup/errors). */
  transactions_excluded: number
  /** Transfer legs imported without their partner. Non-zero means some rows
   *  that are really internal money movement could not be identified as such. */
  transfer_legs_unpaired: number
  /** How many of those are one line of a split — unpairable by design, since
   *  a split's money lives on its parent. The rest are worth chasing. */
  transfer_legs_in_splits: number
  /** Categories tagged Savings from their names — the only key the importer
   *  applies (backend domain/tag_hints.py) — so the savings report has
   *  something to show. The tag changes how a category's spending is
   *  classified, so it is reported rather than applied quietly. */
  categories_tagged: number
  /** Which ones, and why. The count alone cannot answer "show me what you
   *  did", and nothing on the join table records that a tag was guessed. */
  tagged_categories: YnabTaggedCategory[]
  /** YNAB's Credit Card Payments reserves whose card was never imported —
   *  the matched ones become the card's set-aside assignments. */
  credit_card_payment_assignments_skipped: number
  credit_card_payment_reserves_skipped: string
  /** Register rows on tracking accounts whose export line named a category,
   *  imported without one — off-budget activity is net-worth movement. */
  tracking_account_categories_stripped: number
  /** Register rows filed to a Credit Card Payments category — a reserve,
   *  not a spending envelope — imported uncategorized. YNAB never writes
   *  such rows itself; non-zero means the file was unusual. */
  credit_card_payment_categories_stripped: number
  /** Null when the check could not run. */
  parity: YnabParity | null
  /** B — the budget's envelope math starts from YNAB's own position at the
   * month before this (server: YNABImportResult; db.models.ImportAnchor).
   * Top-level, not inside parity: parity may fail, the anchor may not.
   * Absent on pre-feature summaries — render nothing then. */
  anchored_at?: string | null
  anchor_skipped_reason?: string | null
  /** Rows dated after the import, each now a one-off scheduled transaction.
   *  Absent on pre-feature summaries — treat as empty. */
  held_out_future?: YnabHeldOutFuture[]
  held_out_splits_uncategorized?: number
  held_out_transfer_legs_unpaired?: number
  errors: string[]
}

/** The fields a CSV column can be mapped to. `amount` carries its own sign;
 *  `debit`/`credit` are the other shape, where the sign is which column the
 *  figure sits in. */
export type CsvField = 'date' | 'payee' | 'amount' | 'debit' | 'credit' | 'memo' | 'category'

export type CsvMapping = Partial<Record<CsvField, string>>

export interface CsvPreviewRow {
  line: number
  date: string
  amount: number
  payee: string
  memo: string | null
  category: string | null
  /** Already in this account. The reason the preview exists. */
  duplicate: boolean
}

export interface CsvPreview {
  headers: string[]
  mapping: CsvMapping
  date_format: string | null
  total_rows: number
  new_rows: number
  duplicate_rows: number
  skipped: { line: number; reason: string }[]
  sample: CsvPreviewRow[]
}

function csvBody(file: File, accountId: string, mapping?: CsvMapping) {
  const formData = new FormData()
  formData.append('file', file)
  const params: Record<string, string> = { account_id: accountId }
  // Omitted entirely when unset, so the server falls back to its own guess
  // rather than being handed an empty object meaning "map nothing".
  if (mapping && Object.keys(mapping).length) params.mapping = JSON.stringify(mapping)
  return { formData, params }
}

export async function previewCsv(
  budgetId: string,
  accountId: string,
  file: File,
  mapping?: CsvMapping
): Promise<CsvPreview> {
  const { formData, params } = csvBody(file, accountId, mapping)
  const { data } = await apiClient.post<CsvPreview>(`/${budgetId}/import/csv/preview`, formData, {
    params,
  })
  return data
}

export async function importCsv(
  budgetId: string,
  accountId: string,
  file: File,
  mapping?: CsvMapping
): Promise<CsvImportResult> {
  const { formData, params } = csvBody(file, accountId, mapping)
  const { data } = await apiClient.post<CsvImportResult>(`/${budgetId}/import/csv`, formData, {
    params,
  })
  return data
}

/** What an import did, and whether anyone has looked at it yet.
 *
 * `summary` is null for a budget that was not created by a YNAB import, and
 * for one imported before this was recorded. Both are ordinary — the review
 * still opens, it just has nothing to report about the event and goes straight
 * to what can still be changed. */
export interface ImportSummary {
  summary: YnabImportResult | null
  reviewed_at: string | null
}

export const importSummaryKey = (budgetId: string | null) => [ROOT.importSummary, budgetId]

export function useImportSummary(budgetId: string | null) {
  return useQuery({
    queryKey: importSummaryKey(budgetId),
    queryFn: async () => {
      const { data } = await apiClient.get<ImportSummary>(`/${budgetId}/import-summary`)
      return data
    },
    enabled: !!budgetId,
    // A record of a past event — but not a single one. A second import or a
    // snapshot restore writes a new summary onto the same budget, and with
    // `Infinity` the old one was pinned until a page reload. Both of those
    // paths now go through `invalidateAfterImport`; the finite staleTime is
    // the belt to that braces.
    staleTime: 60_000,
  })
}

/** Stamp the review as seen, so it stops opening unasked.
 *
 * It stays reachable afterwards — this governs only whether it appears by
 * itself. */
export function useMarkImportReviewed(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post(`/${budgetId}/import-summary/reviewed`),
    onSuccess: () => qc.invalidateQueries({ queryKey: importSummaryKey(budgetId) }),
  })
}
