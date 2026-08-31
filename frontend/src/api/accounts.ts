import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { Account, AccountType } from '../types'
import { ROOT } from './queryKeys'

export interface AccountCreate {
  name: string
  account_type: AccountType
  on_budget?: boolean
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
export interface HygieneFinding {
  /** Stable key, so the UI routes the fix without parsing prose. */
  kind: string
  title: string
  detail: string
  action: string
  account_ids: string[]
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
