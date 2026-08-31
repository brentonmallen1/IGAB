import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
import type { SignalKey } from '../content/roadmap'
import { ROOT } from './queryKeys'

/** How a concept came to be answered. */
export type SignalSource =
  | 'auto'
  | 'manual'
  | 'external'
  | 'manual+external'
  | 'dismissed'
  | 'answer'
  /** Personalisation is switched off — no detection ran. */
  | 'off'

export type EntityType = 'category' | 'account' | 'liability'

export interface ConceptInfo {
  key: SignalKey
  label: string
  kind: 'amount' | 'rate' | 'boolean'
  binds_to: EntityType[]
  prompt: string
  caveat: string
  auto: boolean
  allows_external: boolean
  us_only: boolean
  aliases: string[]
}

export interface Signal {
  key: SignalKey
  tracked: boolean
  source: SignalSource
  /** null whenever detection could not tell. Never a guess. */
  met: boolean | null
  /** Detected plus self-reported. Strings: these are money, not floats. */
  value: string | null
  detected_value: string | null
  external_value: string | null
  external_declared: boolean
  external_as_of: string | null
  target: string | null
  /** Emergency fund only: the starter cushion ($1,000 or one month of
   *  essentials, whichever is larger) and whether the fund clears it. The
   *  roadmap's starter step reads these; the full step reads `target`/`met`. */
  starter_target: string | null
  starter_met: boolean | null
  reason: string
  entities: Partial<Record<EntityType, string[]>>
  /** Things that did not count and should be said out loud — a debt with no
   *  rate on record. A gap in the data is a nudge, not a silence. */
  gaps: string[]
  note: string | null
}

export interface SignalsResponse {
  personalization: boolean
  concepts: Signal[]
}

export interface GuidePreferences {
  personalization: boolean
  checkup: boolean
  wishlist: boolean
}

export interface GuideOverview {
  concepts: ConceptInfo[]
  thresholds: Record<string, number>
  preferences: GuidePreferences
  progress: Record<string, 'done' | 'skipped'>
}

export interface CandidateOption {
  id: string
  name: string
  detail?: string | null
}

export interface BindingUpdate {
  mode: 'auto' | 'manual' | 'dismissed' | 'answer' | 'external'
  entity_ids?: Partial<Record<EntityType, string[]>>
  answer?: boolean
  external?: boolean
  /** Optional on purpose — "I have this covered" is a complete answer. */
  external_amount?: string | null
  note?: string | null
}

export function useGuideOverview(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.guide, budgetId],
    queryFn: () => apiClient.get<GuideOverview>(`/${budgetId}/guide`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useGuideSignals(budgetId: string | null, enabled = true) {
  return useQuery({
    queryKey: [ROOT.guideSignals, budgetId],
    queryFn: () =>
      apiClient.get<SignalsResponse>(`/${budgetId}/guide/signals`).then((r) => r.data),
    enabled: !!budgetId && enabled,
    // Signals are derived from the whole budget, so almost any edit could move
    // them. Short and refetched on demand rather than aggressively live.
    staleTime: 30_000,
  })
}

export function useConceptCandidates(budgetId: string | null, conceptKey: string | null) {
  return useQuery({
    queryKey: [ROOT.guideCandidates, budgetId, conceptKey],
    queryFn: () =>
      apiClient
        .get<{ concept_key: string; options: Partial<Record<EntityType, CandidateOption[]>> }>(
          `/${budgetId}/guide/candidates/${conceptKey}`
        )
        .then((r) => r.data.options),
    enabled: !!budgetId && !!conceptKey,
    staleTime: 60_000,
  })
}

export function useSetBinding(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ conceptKey, ...body }: BindingUpdate & { conceptKey: string }) =>
      apiClient.put(`/${budgetId}/guide/bindings/${conceptKey}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.guideSignals, budgetId] }),
  })
}

/** What turning the Wishlist off would return to Ready to Assign.
 *
 *  Served, not summed here from the month's balances: the switch and the
 *  endpoint have to agree on the figure, and once the group is archived the
 *  client cannot see its envelopes to add them up at all. */
export interface WishlistRetirePreview {
  envelopes: string[]
  available: string
  is_empty: boolean
}

/** Asked at the moment the switch is clicked, not held in a cache: the answer
 *  is a money figure the dialog is about to state, and a stale one would name
 *  an amount that is no longer there. */
export function fetchWishlistRetirePreview(budgetId: string) {
  return apiClient
    .get<WishlistRetirePreview>(`/${budgetId}/guide/wishlist/retire-preview`)
    .then((r) => r.data)
}

export function useSetGuidePreferences(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (
      changes: Partial<GuidePreferences> & { release_wishlist_money?: boolean }
    ) =>
      apiClient
        .put<GuidePreferences>(`/${budgetId}/guide/preferences`, changes)
        .then((r) => r.data),
    onSuccess: (prefs) => {
      // Seed rather than only invalidate: the toggle should settle instantly,
      // and the server may have forced checkup off alongside personalisation.
      qc.setQueryData<GuideOverview | undefined>([ROOT.guide, budgetId], (old) =>
        old ? { ...old, preferences: prefs } : old
      )
      qc.invalidateQueries({ queryKey: [ROOT.guide, budgetId] })
      qc.invalidateQueries({ queryKey: [ROOT.guideSignals, budgetId] })
    },
    // The server refuses a wishlist-off that would move money without an
    // explicit confirmation, and its sentence carries the figure. A silent
    // failure here would look like a switch that simply does not work.
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not save that setting')),
  })
}

export function useSetGuideStep(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ stageId, state }: { stageId: string; state: 'done' | 'skipped' | null }) =>
      apiClient.put(`/${budgetId}/guide/progress/${stageId}`, { state }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.guide, budgetId] }),
  })
}

// ── the checkup ──────────────────────────────────────────────────────────────

/** What the health report can find. Home of each kind → roadmap step:
 *  components/guide/checkupLeds.ts. */
export type FindingKind =
  | 'high_interest_debt'
  | 'ef_not_started'
  | 'ef_below_starter'
  | 'chronic_overspend'
  | 'ef_below_full'
  | 'moderate_debt'
  | 'retirement_below_target'
  | 'stale_external'
  | 'unknown_rates'

export interface CheckupFinding {
  kind: FindingKind
  /** Severity, 1 = most. The server sorts by it; the client shows the first few. */
  rank: number
  concept_key: string | null
  /** A short clause with no figures — compose with `value` in the budget's currency. */
  title: string
  detail: string
  value: string | null
  target: string | null
  names: string[]
}

export interface CheckupMetric {
  key: string
  label: string
  value: string | null
  target: string | null
  unit: 'money' | 'months' | 'percent' | 'count'
  detail: string
  /** Finding kinds this row is the home of — mark it when one fired. */
  finding_kinds: FindingKind[]
  /** A report tab with the numbers behind this row, when one exists. */
  report: string | null
  /** What the figure counts, by name — the whole list; NameChips paces it. */
  names: string[]
  /** The same figure in money when `unit` is not money — the emergency fund
   *  in months also says what those months are worth. */
  money_value: string | null
  money_target: string | null
}

export interface Checkup {
  enabled: boolean
  as_of: string
  last_run: string | null
  metrics: CheckupMetric[]
  /** Every finding that fired, most severe first — never capped by the server. */
  findings: CheckupFinding[]
}

export function useGuideCheckup(budgetId: string | null, enabled = true) {
  return useQuery({
    queryKey: [ROOT.guideCheckup, budgetId],
    queryFn: () => apiClient.get<Checkup>(`/${budgetId}/guide/checkup`).then((r) => r.data),
    // Gated on the preference by the caller: with reviews off, no request at all.
    enabled: !!budgetId && enabled,
    staleTime: 30_000,
  })
}

export function useRunHealthReport(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient.post<Checkup>(`/${budgetId}/guide/checkup/run`).then((r) => r.data),
    // The run returns the same payload the GET would, freshly stamped.
    onSuccess: (checkup) => qc.setQueryData([ROOT.guideCheckup, budgetId], checkup),
  })
}


// ── scenario calculators ─────────────────────────────────────────────────────
// Inputs are documents the user typed (or edited from a seed), so these are
// POSTs behind useQuery: keyed on the body, previous answer kept while the next
// one is in flight. Money and rates travel as strings, never floats.

export interface CascadeDebtIn {
  key: string
  name: string
  balance: string
  annual_rate: string
  minimum_payment: string
}

export interface PayoffPlanRequest {
  debts: CascadeDebtIn[]
  extra: string
}

export interface CascadeDebtOut {
  key: string
  name: string
  order: number
  payoff_date: string | null
  months: number
  never_pays_off: boolean
  total_interest: string
  total_principal: string
}

export interface CascadeMonthOut {
  month_index: number
  date: string
  payment: string
  principal_paid: string
  interest_paid: string
  balance: string
  balances: Record<string, string>
}

export interface CascadeOut {
  order: 'avalanche' | 'snowball'
  debts: CascadeDebtOut[]
  months: CascadeMonthOut[]
  debt_free_date: string | null
  never_pays_off: boolean
  total_interest: string
  total_paid: string
}

export interface PayoffPlanResponse {
  as_of: string
  extra: string
  avalanche: CascadeOut
  snowball: CascadeOut
  /** Minimums only, nothing rolled — what happens if nothing changes. */
  minimums_only: CascadeOut
}

export interface PayVsSaveRequest {
  balance: string
  annual_rate: string
  minimum_payment: string
  extra: string
  savings_apy: string
}

export interface PayVsSaveResponse {
  horizon_months: number
  baseline_total_interest: string
  baseline_never_pays_off: boolean
  pay_months: number
  pay_payoff_date: string | null
  pay_total_interest: string
  pay_never_pays_off: boolean
  debt_interest_saved: string
  months_sooner: number
  savings_contributed: string
  savings_balance: string
  savings_interest_earned: string
  breakeven_apy: string | null
  favours: 'pay' | 'save' | 'even'
}

export interface LoanIn {
  name: string
  principal: string
  annual_rate: string
  term_months?: number | null
  payment?: string | null
  fees?: string
}

export interface LoanCompareRequest {
  loans: LoanIn[]
}

export interface LoanOutcomeOut {
  name: string
  payment: string
  months: number
  payoff_date: string | null
  never_pays_off: boolean
  total_interest: string
  total_cost: string
}

export interface LoanCompareResponse {
  loans: LoanOutcomeOut[]
  cheapest: string | null
}

export interface EmergencyFundRequest {
  months: number
  monthly_contribution: string
}

export interface EmergencyFundResponse {
  months: number
  monthly_contribution: string
  essentials_monthly: string | null
  current: string | null
  target: string | null
  gap: string | null
  months_to_fund: number | null
  funded_by: string | null
}

function useScenario<Req, Res>(kind: string, budgetId: string | null, body: Req | null) {
  return useQuery({
    queryKey: [ROOT.guideScenario, kind, budgetId, body],
    queryFn: () =>
      apiClient
        .post<Res>(`/${budgetId}/guide/scenarios/${kind}`, body)
        .then((r) => r.data),
    enabled: !!budgetId && body !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

export function usePayoffPlan(budgetId: string | null, body: PayoffPlanRequest | null) {
  return useScenario<PayoffPlanRequest, PayoffPlanResponse>('payoff-plan', budgetId, body)
}

export function usePayVsSave(budgetId: string | null, body: PayVsSaveRequest | null) {
  return useScenario<PayVsSaveRequest, PayVsSaveResponse>('pay-vs-save', budgetId, body)
}

export function useLoanCompare(budgetId: string | null, body: LoanCompareRequest | null) {
  return useScenario<LoanCompareRequest, LoanCompareResponse>('loan-compare', budgetId, body)
}

export function useEmergencyFundPlan(
  budgetId: string | null,
  body: EmergencyFundRequest | null
) {
  return useScenario<EmergencyFundRequest, EmergencyFundResponse>('emergency-fund', budgetId, body)
}
