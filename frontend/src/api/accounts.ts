import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { invalidateAfterTransactionChange } from './invalidateAfterTransactionChange'
import type { Account, AccountType } from '../types'
import { ROOT } from './queryKeys'

export interface AccountCreate {
  name: string
  account_type: AccountType
  on_budget?: boolean
  /** Omitted takes the type's default_counts_as_savings. */
  counts_as_savings?: boolean
  /** Valid only on an off-budget asset that counts as savings; the server
   *  refuses it anywhere else (`canCountTowardEmergencyFund`). */
  counts_toward_emergency_fund?: boolean
  note?: string
  sort_order?: number
}

export async function fetchAccounts(budgetId: string, include_closed = false): Promise<Account[]> {
  const { data } = await apiClient.get<Account[]>(`/${budgetId}/accounts`, {
    params: { include_closed },
  })
  return data
}

export function useAccounts(budgetId: string | null, options?: { includeClosed?: boolean }) {
  const includeClosed = options?.includeClosed ?? false
  return useQuery({
    queryKey: [ROOT.accounts, budgetId, { includeClosed }],
    queryFn: () => fetchAccounts(budgetId!, includeClosed),
    enabled: !!budgetId,
    staleTime: 30_000,
  })
}

export function useCreateAccount(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: AccountCreate) =>
      apiClient.post<Account>(`/${budgetId}/accounts`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.accounts, budgetId] })
    },
  })
}

export function useUpdateAccount(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...data }: Partial<Account> & { id: string }) =>
      apiClient.patch<Account>(`/accounts/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.accounts, budgetId] })
    },
  })
}

export function useDeleteAccount(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    // `liability` decides what becomes of the debt a liability account was
    // tracking: kept as a manually tracked one (the default and the
    // non-destructive branch) or removed with the account.
    mutationFn: ({
      accountId,
      liability = 'keep',
    }: {
      accountId: string
      liability?: 'keep' | 'delete'
    }) => apiClient.delete(`/accounts/${accountId}`, { params: { liability } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.accounts, budgetId] })
      // Either disposition rewrites the companion, and both liability views
      // read it — the sidebar's debt section included.
      qc.invalidateQueries({ queryKey: [ROOT.liabilities, budgetId] })
    },
  })
}

export function useScanDuplicates() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (accountId: string) =>
      apiClient
        .post<{ created: number }>(`/accounts/${accountId}/scan-duplicates`)
        .then((r) => r.data),
    onSuccess: (_data, accountId) => {
      qc.invalidateQueries({ queryKey: [ROOT.pendingMatchesAccount, accountId] })
    },
  })
}

/** One thing about this budget's accounts that is probably wrong. */
/** One thing a finding is about. Figures arrive raw (a decimal string, an
 *  ISO date) and are formatted here — see `services/account_hygiene.py
 *  FindingItem`; a sentence the server wrote could not follow the user's
 *  currency format, which is how "58.6800" reached the screen. */
export interface FindingItem {
  label: string
  amount: string | null
  /** First of the month the item is about. */
  month: string | null
  /** A row's date. */
  day: string | null
  note: string | null
  /** What to do about this item, when it differs from the finding's action. */
  fix: string | null
  account_id: string | null
  transaction_id: string | null
  /** The rows a bulk action would touch — for unlinked card payments,
   *  `[outflow, inflow]`. */
  transaction_ids: string[]
}

export interface HygieneFinding {
  /** Stable key, so the UI routes the fix without parsing prose. */
  kind: string
  title: string
  /** One sentence: what is wrong. */
  summary: string
  /** What to do, in a sentence or two. */
  action: string
  items: FindingItem[]
  /** The reasoning, drawn collapsed. */
  why: string | null
  account_ids: string[]
  /** Valued Assets are not accounts; findings about one route to /assets/{id}. */
  asset_ids: string[]
  transaction_count: number
}

export interface HygieneReport {
  findings: HygieneFinding[]
  clean: boolean
}

/**
 * Post-import account hygiene. Separate from `/integrity`, which reports
 * invariant violations — everything here is a judgement call the user can
 * dismiss, and a clean integrity run has to keep meaning "the maths is sound".
 */
export function useAccountHygiene(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.accountHygiene, budgetId],
    queryFn: () =>
      apiClient.get<HygieneReport>(`/${budgetId}/accounts/hygiene`).then((r) => r.data),
    enabled: !!budgetId,
  })
}

export interface RepairTransfersResult {
  linked: number
  ambiguous: number
  remaining: number
}

export interface RepairTrackingCategoriesResult {
  stripped: number
}

/** Strip categories from rows on off-budget accounts. Those categories count
 *  nowhere — the budget's sums exclude off-budget rows — so this moves no
 *  money; it makes the register agree with the budget. One undoable batch. */
export function useRepairTrackingCategories(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient
        .post<RepairTrackingCategoriesResult>(
          `/${budgetId}/accounts/hygiene/repair-tracking-categories`
        )
        .then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.transactions] })
      qc.invalidateQueries({ queryKey: [ROOT.allTransactions] })
      qc.invalidateQueries({ queryKey: [ROOT.accountHygiene, budgetId] })
    },
  })
}

/** Link the unpaired transfer legs whose partner is unmistakable.
 *
 *  Repairs history the fixed importer cannot reach. Writes no money and
 *  creates no rows — only the link — so it is safe to run and safe to undo,
 *  and anything ambiguous is left for the register's picker. */
export function useRepairTransfers(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient
        .post<RepairTransfersResult>(`/${budgetId}/accounts/hygiene/repair-transfers`)
        .then((r) => r.data),
    onSuccess: () => {
      // Links change how every transfer row reads and what the register's
      // unpaired filter returns.
      qc.invalidateQueries({ queryKey: [ROOT.transactions] })
      qc.invalidateQueries({ queryKey: [ROOT.allTransactions] })
      qc.invalidateQueries({ queryKey: [ROOT.accountHygiene, budgetId] })
    },
  })
}

export interface LinkCardPaymentsResult {
  linked: number
  /** Confirmed pairs the server no longer reports — left alone. */
  skipped: number
}

/** Link the unlinked card payments a person confirmed, as one undo. The
 *  server re-derives the pairs and refuses any it does not report. */
export function useLinkCardPayments(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (pairs: string[][]) =>
      apiClient
        .post<LinkCardPaymentsResult>(`/${budgetId}/accounts/hygiene/link-card-payments`, {
          pairs,
        })
        .then((r) => r.data),
    // Linking clears the cash leg's envelope and spends the card's Set aside,
    // so envelopes, cards and Ready to Assign all move — not just the rows.
    onSuccess: () => invalidateAfterTransactionChange(qc, { budgetId }),
  })
}

export interface AccountSecrets {
  account_number: string | null
  routing_number: string | null
}

/** The decrypted reference numbers, fetched only when the eye is clicked —
 *  never cached in a listing. */
export async function fetchAccountSecrets(accountId: string): Promise<AccountSecrets> {
  const { data } = await apiClient.get<AccountSecrets>(`/accounts/${accountId}/secrets`)
  return data
}
