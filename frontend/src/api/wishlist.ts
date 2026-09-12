import toast from 'react-hot-toast'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, apiErrorMessage } from './client'
import { invalidateAfterCategoryChange } from './invalidateAfterCategoryChange'
import { ROOT } from './queryKeys'

// The wishlist lives inside the budget: a wish's money is an envelope's
// money. Everything below is served — reach, rollups, cooling, review-due —
// and the client only sorts, filters and formats it. Money arrives as a JSON
// number, like every `ApiModel` response (backend `schemas/base.py`). These
// said `string` long after that stopped being true, and the edit form seeded
// its Cost input from one: Save called `.trim()` on a number and threw before
// any request was sent.

export type FundingMode = 'own' | 'existing' | 'none'
export type WishStatus = 'open' | 'done' | 'dropped'
export type ReachState = 'now' | 'months' | 'no_rate' | 'unlinked'

export interface WishFunding {
  mode: FundingMode
  category_id: string | null
  category_name: string | null
  /** The envelope came from the project rather than the wish itself. */
  inherited: boolean
  /** The wishlist created this envelope; deleting the wish offers to delete it. */
  owns_envelope: boolean
  target_date: string | null
}

export interface WishReach {
  state: ReachState
  months: number | null
  date: string | null
  /** What the wishes ahead in the same envelope still need. */
  ahead_cost: number
  /** 0–1, net of the wishes ahead. */
  progress: number
}

export interface Wish {
  id: string
  project_id: string | null
  name: string
  url: string | null
  notes: string | null
  cost: number
  priority: number
  /** Pinned as a top priority — an explicit choice, capped at the served
   *  `priority_limit`; distinct from `priority`, the funding-queue order. */
  is_priority: boolean
  status: WishStatus
  funding: WishFunding
  cooling_until: string | null
  cooling: boolean
  /** The day the wish was added, in the person's own date: what a cooling-off
   *  in days counts from. Served, because `created_at` is an instant and the
   *  day it falls on depends on a timezone the server recorded at creation. */
  added_on: string
  last_affirmed_at: string | null
  review_due: boolean
  done_at: string | null
  created_at: string
  reach: WishReach | null
}

export type ProjectState =
  'now' | 'months' | 'no_rate' | 'unlinked' | 'mixed' | 'complete' | 'empty'

export interface ProjectSummary {
  item_count: number
  open_count: number
  total_cost: number
  affordable_now: number
  funded_by: string | null
  state: ProjectState
  complete: boolean
}

export interface WishlistProject {
  id: string
  name: string
  category_id: string | null
  category_name: string | null
  notes: string | null
  sort_order: number
  summary: ProjectSummary
}

export interface DrainAffected {
  item_id: string
  name: string
  months_further: number | null
}

export interface DrainMove {
  move_id: string
  month: string
  date: string
  amount: number
  from_category_id: string
  from_name: string
  to_category_id: string | null
  to_name: string
  affected: DrainAffected[]
}

export interface Drains {
  month: string
  total: number
  moves: DrainMove[]
}

export interface WishlistSettings {
  cooling_days: number
  review_after_days: number
}

export interface Wishlist {
  enabled: boolean
  items: Wish[]
  history: Wish[]
  projects: WishlistProject[]
  still_wanted: { count: number; of: number; months: number }
  review_due_count: number
  settings: WishlistSettings
  /** The pin cap, served — the client never spells its own 3. */
  priority_limit: number
  /** The longest cooling-off in days, served for the same reason. */
  max_cooling_days: number
  drains: Drains | null
}

export interface FundingIn {
  mode: FundingMode
  category_id?: string | null
  want_by?: string | null
}

export interface WishCreate {
  name: string
  cost: number
  url?: string | null
  notes?: string | null
  project_id?: string | null
  priority?: number | null
  cooling_days?: number | null
  /** The browser's today: the day the wish is added, which a cooling-off in
   *  days counts from now and on every later edit. */
  client_today?: string
  funding: FundingIn
}

export interface WishUpdate {
  name?: string
  cost?: number
  url?: string | null
  notes?: string | null
  project_id?: string | null
  priority?: number
  is_priority?: boolean
  status?: WishStatus
  cooling_until?: string | null
  /** The cooling-off as days after the wish was added — the other spelling of
   *  `cooling_until`. The server resolves the date and refuses both at once. */
  cooling_days?: number
  funding?: FundingIn
}

export interface ProjectCreate {
  name: string
  category_id?: string | null
  notes?: string | null
}

export interface ProjectUpdate {
  name?: string
  category_id?: string | null
  notes?: string | null
}

/** The envelope a deleted wish owned, offered for deletion with it. */
export interface WishEnvelope {
  category_id: string
  name: string
  available: number
}

export interface DeleteWishResult {
  envelope: WishEnvelope | null
}

export function useWishlist(budgetId: string | null, enabled = true) {
  return useQuery({
    queryKey: [ROOT.wishlist, budgetId],
    queryFn: () => apiClient.get<Wishlist>(`/${budgetId}/wishlist`).then((r) => r.data),
    enabled: !!budgetId && enabled,
    staleTime: 30_000,
  })
}

function useWishlistMutation<TVars, TResult>(
  budgetId: string,
  fn: (vars: TVars) => Promise<TResult>,
  failure: string,
  quiet = false
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.wishlist, budgetId] })
      // An own envelope is a real category with a goal: the budget page and
      // every picker need to hear about it.
      invalidateAfterCategoryChange(qc, budgetId)
    },
    onError: quiet ? undefined : (e) => toast.error(apiErrorMessage(e, failure)),
  })
}

export function useCreateWish(budgetId: string) {
  // Quiet: the form shows the server's reason inline (a name clash, say).
  return useWishlistMutation<WishCreate, Wish>(
    budgetId,
    (body) => apiClient.post<Wish>(`/${budgetId}/wishlist`, body).then((r) => r.data),
    'Could not add the wish',
    true
  )
}

export function useUpdateWish(budgetId: string) {
  return useWishlistMutation<{ id: string } & WishUpdate, Wish>(
    budgetId,
    ({ id, ...body }) =>
      apiClient.patch<Wish>(`/${budgetId}/wishlist/${id}`, body).then((r) => r.data),
    'Could not save the wish'
  )
}

export function useDeleteWish(budgetId: string) {
  return useWishlistMutation<string, DeleteWishResult>(
    budgetId,
    (id) => apiClient.delete<DeleteWishResult>(`/${budgetId}/wishlist/${id}`).then((r) => r.data),
    'Could not delete the wish'
  )
}

export function useAffirmWish(budgetId: string) {
  return useWishlistMutation<string, void>(
    budgetId,
    (id) => apiClient.post(`/${budgetId}/wishlist/${id}/affirm`).then(() => undefined),
    'Could not save'
  )
}

export function useReorderWishes(budgetId: string) {
  return useWishlistMutation<string[], void>(
    budgetId,
    (item_ids) =>
      apiClient.post(`/${budgetId}/wishlist/reorder`, { item_ids }).then(() => undefined),
    'Could not reorder'
  )
}

export function useCreateProject(budgetId: string) {
  return useWishlistMutation<ProjectCreate, WishlistProject>(
    budgetId,
    (body) =>
      apiClient.post<WishlistProject>(`/${budgetId}/wishlist/projects`, body).then((r) => r.data),
    'Could not add the project',
    true
  )
}

export function useUpdateProject(budgetId: string) {
  return useWishlistMutation<{ id: string } & ProjectUpdate, WishlistProject>(
    budgetId,
    ({ id, ...body }) =>
      apiClient
        .patch<WishlistProject>(`/${budgetId}/wishlist/projects/${id}`, body)
        .then((r) => r.data),
    'Could not save the project'
  )
}

export function useDeleteProject(budgetId: string) {
  return useWishlistMutation<string, void>(
    budgetId,
    (id) => apiClient.delete(`/${budgetId}/wishlist/projects/${id}`).then(() => undefined),
    'Could not delete the project'
  )
}

export function useReorderProjects(budgetId: string) {
  return useWishlistMutation<string[], void>(
    budgetId,
    (project_ids) =>
      apiClient
        .post(`/${budgetId}/wishlist/projects/reorder`, { project_ids })
        .then(() => undefined),
    'Could not reorder'
  )
}

export function useSetWishlistSettings(budgetId: string) {
  return useWishlistMutation<Partial<WishlistSettings>, WishlistSettings>(
    budgetId,
    (body) =>
      apiClient.put<WishlistSettings>(`/${budgetId}/wishlist/settings`, body).then((r) => r.data),
    'Could not save settings'
  )
}
