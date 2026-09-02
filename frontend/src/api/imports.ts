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
  /** Categories tagged Savings / Long-term expense from their names, so the
   *  savings report has something to show. A tag changes how a category's
   *  spending is classified, so it is reported rather than applied quietly. */
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
  errors: string[]
}

export async function importCsv(
  budgetId: string,
  accountId: string,
  file: File
): Promise<CsvImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<CsvImportResult>(`/${budgetId}/import/csv`, formData, {
    params: { account_id: accountId },
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
