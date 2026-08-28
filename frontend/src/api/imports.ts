import { apiClient } from './client'

export interface CsvImportResult {
  imported: number
  skipped: number
  errors: string[]
  /** Change-log batch id for undo (null if nothing was imported). */
  batch_id: string | null
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
  /** Categories tagged Savings / Long-term expense from their names, so the
   *  savings report has something to show. A tag changes how a category's
   *  spending is classified, so it is reported rather than applied quietly. */
  categories_tagged: number
  /** YNAB's Credit Card Payments reserves, left out on purpose: IGAB nets a
   *  card's balance against cash in Ready to Assign, so importing them would
   *  reserve the same debt twice. The money is what Ready to Assign keeps. */
  credit_card_payment_assignments_skipped: number
  credit_card_payment_reserves_skipped: string
  errors: string[]
}

const MULTIPART_HEADERS = { 'Content-Type': undefined }

export async function importCsv(
  budgetId: string,
  accountId: string,
  file: File
): Promise<CsvImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await apiClient.post<CsvImportResult>(`/${budgetId}/import/csv`, formData, {
    params: { account_id: accountId },
    headers: MULTIPART_HEADERS,
  })
  return data
}
