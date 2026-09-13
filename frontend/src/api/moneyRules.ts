import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'

/**
 * "How money counts", answered by the server's own classifier
 * (`backend/src/igab/domain/money_moves.py`). Nothing here decides a class, a
 * report family or a budget term — the client renders what is served, so the
 * explorer cannot teach a rule the reports do not run.
 */

export type Classification = 'asset' | 'liability'
export type MoveKind = 'transfer' | 'transaction'
export type MoveDirection = 'in' | 'out'
export type CategoryKind = 'none' | 'ordinary' | 'savings' | 'debt_principal' | 'income'
export type LegRole = 'from' | 'to' | 'account'
export type BudgetTerm = 'ready_to_assign' | 'envelope' | 'card_set_aside' | 'card_uncovered'
export type ReportFamily =
  'income' | 'spending' | 'cost_of_living' | 'savings_rate' | 'savings_rate_with_debt'

export interface AccountShapeIn {
  classification: Classification
  on_budget: boolean
  counts_as_savings: boolean
}

export interface MoneyMoveRequest {
  kind: MoveKind
  /** The from-account of a transfer, or the one account of a transaction. */
  account: AccountShapeIn
  to_account?: AccountShapeIn | null
  direction?: MoveDirection | null
  category: CategoryKind
  amount: number
}

export interface MonthMoveRequest extends MoneyMoveRequest {
  label: string
}

export interface MoneyLeg {
  role: LegRole
  on_budget: boolean
  amount: number
  category: CategoryKind
  cls: string
  class_label: string
  reason: string
  reason_text: string
  counted_in: ReportFamily[]
  /** A Savings-tagged outflow: plan reports count it as spent regardless. */
  planned_spend_by_tag: boolean
}

export interface MoneyFigures {
  income: number
  spending: number
  cost_of_living: number
  savings: number
  debt_principal: number
  savings_rate: number | null
  savings_rate_with_debt: number | null
}

export interface MoveExplanation {
  /** Which leg may carry a category; null when neither may. */
  category_role: LegRole | null
  category_applied: boolean
  legs: MoneyLeg[]
  budget_terms: { term: BudgetTerm; delta: number }[]
  class_totals: Record<string, number>
  figures: MoneyFigures
  net_worth_delta: number
  assumption: string
}

export interface MoneyRule {
  position: number
  cls: string
  class_label: string
  reason: string
  reason_text: string
  tag_key: string | null
  is_default: boolean
}

export interface MoneyShape {
  key: string
  label: string
  classification: Classification
  on_budget: boolean
  /** null where the flag changes nothing for this shape. */
  counts_as_savings: boolean | null
  money_in: { description: string; explanation: MoveExplanation }
  money_out: { description: string; explanation: MoveExplanation }
}

export interface MoneyRulesResponse {
  rules: MoneyRule[]
  report_families: { key: ReportFamily; label: string; classes: string[] }[]
  shapes: MoneyShape[]
  planned_spend_tag_keys: string[]
}

export interface MoneyMonthResponse {
  rows: { label: string; explanation: MoveExplanation }[]
  class_totals: Record<string, number>
  figures: MoneyFigures
}

export function useMoneyRules(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.guideMoneyRules, budgetId],
    queryFn: () =>
      apiClient.get<MoneyRulesResponse>(`/${budgetId}/guide/money-rules`).then((r) => r.data),
    enabled: !!budgetId,
    // The rules change only with a deploy.
    staleTime: Infinity,
  })
}

export function useExplainMove(budgetId: string | null, body: MoneyMoveRequest | null) {
  return useQuery({
    queryKey: [ROOT.guideMoneyMove, budgetId, body],
    queryFn: () =>
      apiClient
        .post<MoveExplanation>(`/${budgetId}/guide/money-moves/explain`, body)
        .then((r) => r.data),
    enabled: !!budgetId && body !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
  })
}

export function useMoneyMonth(budgetId: string | null, moves: MonthMoveRequest[] | null) {
  return useQuery({
    queryKey: [ROOT.guideMoneyMonth, budgetId, moves],
    queryFn: () =>
      apiClient
        .post<MoneyMonthResponse>(`/${budgetId}/guide/money-moves/month`, { moves })
        .then((r) => r.data),
    enabled: !!budgetId && moves !== null,
    staleTime: Infinity,
  })
}
