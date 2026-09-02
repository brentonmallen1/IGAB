import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { apiClient, apiErrorMessage } from './client'
import { ROOT } from './queryKeys'

/**
 * Category plans: the Guide's paycheck-by-paycheck planner documents.
 *
 * The list ('list') and one plan ('detail') use distinct sub-keys ON PURPOSE:
 * React Query invalidation prefix-matches, and the planner's autosave must be
 * able to refresh the tab strip (names, updated_at) without refetching the
 * open document — a detail refetch mid-typing would clobber keystrokes. The
 * local draft is the source of truth while the planner is mounted; saves
 * write the response into the detail cache with setQueryData instead.
 */

export type PlanCadence = 'weekly' | 'biweekly' | 'semimonthly' | 'monthly'

export interface PlanItem {
  id: string
  /** A live budget category this row is linked to; null = free-form row. */
  category_id: string | null
  name: string
  due_day: number | null
  /** null means "not entered yet" — never zero. */
  amount_cents: number | null
}

export interface PlanPaycheck {
  id: string
  /** null means "use the even split of the monthly take-home". */
  income_override_cents: number | null
  items: PlanItem[]
}

export interface PlanPayload {
  schema_version: 1
  monthly_income_cents: number
  cadence: PlanCadence
  paycheck_count_override: number | null
  paychecks: PlanPaycheck[]
}

export interface PlanSummary {
  id: string
  name: string
  created_at: string
  updated_at: string
}

export interface CategoryPlan extends PlanSummary {
  payload: PlanPayload
}

export type ApplyKind =
  | 'set_target'
  | 'update_target'
  | 'create_category'
  | 'skip_existing_type'
  | 'skip_invalid_link'
  | 'skip_draft'

export interface ApplyEntry {
  kind: ApplyKind
  name: string
  category_id: string | null
  /** The monthly-funding amount (money, not cents); null on skips. */
  amount: number | null
  existing_target_type: string | null
  item_ids: string[]
}

export interface ApplyPreview {
  entries: ApplyEntry[]
  targets_set: number
  targets_updated: number
  categories_created: number
  skipped_existing_type: number
  skipped_invalid_link: number
  skipped_draft: number
}

export interface ApplyResult extends ApplyPreview {
  /** The plan after apply — created/adopted categories linked back in. */
  plan: CategoryPlan
}

const listKey = (budgetId: string | null) => [ROOT.categoryPlans, budgetId, 'list']
const detailKey = (budgetId: string | null, planId: string | null) => [
  ROOT.categoryPlans,
  budgetId,
  'detail',
  planId,
]

export function useCategoryPlans(budgetId: string | null) {
  return useQuery({
    queryKey: listKey(budgetId),
    queryFn: async () => {
      const { data } = await apiClient.get<PlanSummary[]>(`/${budgetId}/category-plans`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function useCategoryPlan(budgetId: string | null, planId: string | null) {
  return useQuery({
    queryKey: detailKey(budgetId, planId),
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryPlan>(`/${budgetId}/category-plans/${planId}`)
      return data
    },
    enabled: !!budgetId && !!planId,
    // The open document must not refetch under the editor; see module note.
    staleTime: Infinity,
  })
}

function useKeepCaches(budgetId: string | null) {
  const qc = useQueryClient()
  return (plan: CategoryPlan) => {
    qc.setQueryData(detailKey(budgetId, plan.id), plan)
    qc.invalidateQueries({ queryKey: listKey(budgetId) })
  }
}

export function useCreatePlan(budgetId: string | null) {
  const keep = useKeepCaches(budgetId)
  return useMutation({
    mutationFn: async (body: { name?: string; payload?: PlanPayload }) => {
      const { data } = await apiClient.post<CategoryPlan>(`/${budgetId}/category-plans`, body)
      return data
    },
    onSuccess: keep,
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not create the plan')),
  })
}

export function useSavePlan(budgetId: string | null) {
  const keep = useKeepCaches(budgetId)
  return useMutation({
    mutationFn: async (vars: { planId: string; payload: PlanPayload }) => {
      const { data } = await apiClient.put<CategoryPlan>(
        `/${budgetId}/category-plans/${vars.planId}`,
        { payload: vars.payload }
      )
      return data
    },
    // Autosave has no user gesture to retry from; absorb blips before the
    // status chip says "Couldn't save". Failures stay silent here — the chip
    // reports them, a toast per failed keystroke-save would be noise.
    retry: 2,
    onSuccess: keep,
  })
}

export function useRenamePlan(budgetId: string | null) {
  const keep = useKeepCaches(budgetId)
  return useMutation({
    mutationFn: async (vars: { planId: string; name: string }) => {
      const { data } = await apiClient.patch<CategoryPlan>(
        `/${budgetId}/category-plans/${vars.planId}`,
        { name: vars.name }
      )
      return data
    },
    onSuccess: keep,
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not rename the plan')),
  })
}

export function useDuplicatePlan(budgetId: string | null) {
  const keep = useKeepCaches(budgetId)
  return useMutation({
    mutationFn: async (vars: { planId: string; name?: string }) => {
      const { data } = await apiClient.post<CategoryPlan>(
        `/${budgetId}/category-plans/${vars.planId}/duplicate`,
        vars.name ? { name: vars.name } : {}
      )
      return data
    },
    onSuccess: keep,
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not duplicate the plan')),
  })
}

export function useDeletePlan(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (planId: string) => {
      await apiClient.delete(`/${budgetId}/category-plans/${planId}`)
      return planId
    },
    onSuccess: (planId) => {
      qc.removeQueries({ queryKey: detailKey(budgetId, planId) })
      qc.invalidateQueries({ queryKey: listKey(budgetId) })
    },
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not delete the plan')),
  })
}

export function useApplyPreview(budgetId: string | null) {
  return useMutation({
    mutationFn: async (planId: string) => {
      const { data } = await apiClient.post<ApplyPreview>(
        `/${budgetId}/category-plans/${planId}/apply-targets/preview`
      )
      return data
    },
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not preview the apply')),
  })
}

export function useApplyTargets(budgetId: string | null) {
  const qc = useQueryClient()
  const keep = useKeepCaches(budgetId)
  return useMutation({
    mutationFn: async (planId: string) => {
      const { data } = await apiClient.post<ApplyResult>(
        `/${budgetId}/category-plans/${planId}/apply-targets`
      )
      return data
    },
    onSuccess: (result) => {
      // The write-back linked rows to their categories; the returned plan is
      // the newest document and replaces the draft's baseline.
      keep(result.plan)
      qc.invalidateQueries({ queryKey: [ROOT.categories] })
      qc.invalidateQueries({ queryKey: [ROOT.categoryGroups] })
      qc.invalidateQueries({ queryKey: [ROOT.targets] })
      qc.invalidateQueries({ queryKey: [ROOT.budgetMonth] })
    },
    onError: (e) => toast.error(apiErrorMessage(e, 'Could not apply the plan')),
  })
}
