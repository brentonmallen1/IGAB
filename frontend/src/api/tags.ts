import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { TagColorSlot } from '../components/common/TagChip'
import { ROOT } from './queryKeys'
import { invalidateAfterTagChange } from './invalidateAfterTagChange'
import type { SavingsMode, SavingsRole } from '../types'

export interface Tag {
  id: string
  name: string
  system_key: string | null
  color_slot: TagColorSlot | null
  /** The rows its checklist draws ticked — carrying it, or a tag that implies
   *  it (`category_filters.ticked_on_checklist`). Served: the client cannot
   *  see a category's other tags. */
  category_count: number
  /** False for a tag the app sets itself (the wishlist's) — its checklist is
   *  not offered, and the server refuses a membership write. */
  hand_settable: boolean
}

export interface TagSimple {
  id: string
  name: string
  color_slot: TagColorSlot | null
}

export function useTags(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.tags, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<Tag[]>(`/${budgetId}/tags`)
      return data
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useCreateTag(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; color_slot?: TagColorSlot | null }) =>
      apiClient.post<Tag>(`/${budgetId}/tags`, body).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.tags, budgetId] }),
  })
}

export function useUpdateTag(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string
      name?: string
      color_slot?: TagColorSlot | null
    }) => apiClient.patch<Tag>(`/${budgetId}/tags/${id}`, body).then((r) => r.data),
    onSuccess: () => invalidateAfterTagChange(qc, budgetId),
  })
}

export function useDeleteTag(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/${budgetId}/tags/${id}`),
    onSuccess: () => invalidateAfterTagChange(qc, budgetId),
  })
}

export function useSetCategoryTags(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ categoryId, tagIds }: { categoryId: string; tagIds: string[] }) =>
      apiClient
        .put<TagSimple[]>(`/${budgetId}/categories/${categoryId}/tags`, { tag_ids: tagIds })
        .then((r) => r.data),
    onSuccess: () => invalidateAfterTagChange(qc, budgetId),
  })
}

/** A system tag a category's names point at but it does not carry (nor
 * implies — an Emergency fund category is never offered Savings).
 *
 * Served, not computed here: the hint table is the server's
 * (domain/tag_hints.py), and a second spelling in TypeScript would be free to
 * disagree with it. */
export interface TagSuggestion {
  category_id: string
  system_key: string
  /** The category's own name or its group's — whichever triggered the hint. */
  matched_on: string
  /** Whether an import writes this one — always false now: nothing is tagged
   *  from a name. */
  applied_on_import: boolean
}

export function useTagSuggestions(budgetId: string | null, enabled = true) {
  return useQuery({
    queryKey: [ROOT.tagSuggestions, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<TagSuggestion[]>(`/${budgetId}/tags/suggestions`)
      return data
    },
    enabled: !!budgetId && enabled,
    staleTime: 60_000,
  })
}

/** Set tags on many categories in one request.
 *
 * The import review changes a dozen categories in a single decision, and each
 * one is a classification override; a dozen requests would leave the budget
 * half-reviewed if one failed. Each entry carries the category's FULL intended
 * tag set — the server replaces rather than merges. */
export function useBulkSetCategoryTags(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (updates: { category_id: string; tag_ids: string[] }[]) =>
      apiClient.put(`/${budgetId}/categories/tags`, { updates }),
    onSuccess: () => invalidateAfterTagChange(qc, budgetId),
  })
}

// `useSetPayeeTags`, `useBulkAddPayeeTags` and `CATEGORY_ONLY_SYSTEM_KEYS`
// lived here. Tags on payees are retired: `ESSENTIAL_TAGGED` was the last rule
// that read one for meaning and it reads categories alone now, so the routes
// they called are gone. The category-only set went with them — every tag is
// category-only, so a list of the exceptions has nothing to say.

export interface TagNotice {
  key: string
  payload: Record<string, unknown>
}

/** One-time notices a migration left about tags (a membership it removed). */
export function useTagNotices(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.tags, budgetId, 'notices'],
    queryFn: async () => {
      const { data } = await apiClient.get<TagNotice[]>(`/${budgetId}/tags/notices`)
      return data
    },
    enabled: !!budgetId,
  })
}

export function useDismissTagNotice(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => apiClient.delete(`/${budgetId}/tags/notices/${key}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ROOT.tags, budgetId, 'notices'] }),
  })
}

// ── one tag's checklist ─────────────────────────────────────────────────────

/** One row of a tag's checklist: every category it could be on, member or
 *  not — an archived one only while it carries the tag. Served by
 *  `GET /tags/{id}/membership` (services/tag_membership.py). */
export interface MembershipCategory {
  id: string
  name: string
  group_id: string
  group_name: string
  is_archived: boolean
  /** Carries the tag itself — the half a person can untick. */
  member: boolean
  /** The name of a tag on this category that implies this one: "Essential" on
   *  the Cost of living checklist, "Emergency fund" on the Savings one
   *  (backend domain/tag_implication.py). The row counts as tagged whatever
   *  `member` says, so it is drawn ticked and locked, and a save never names
   *  it. Served: the client cannot see a row's other tags. */
  implied_by: string | null
  /** `category_filters.SAVINGS_ROLE` as it stands now. */
  savings_role: SavingsRole
  /** The stored choice; null lets the tags decide. */
  savings_mode: SavingsMode | null
}

export interface TagMembership {
  tag: {
    id: string
    name: string
    system_key: string | null
    /** Carrying it makes a category a savings category — each checked row
     *  then says how its money counts as saved. */
    savings_tag: boolean
  }
  categories: MembershipCategory[]
}

/** A diff against the checklist as loaded — see `membershipList.ts`. */
export interface MembershipChange {
  add: string[]
  remove: string[]
  savings_modes: Record<string, SavingsMode | null>
}

export function useTagMembership(budgetId: string | null, tagId: string | null) {
  return useQuery({
    queryKey: [ROOT.tags, budgetId, 'membership', tagId],
    queryFn: () =>
      apiClient.get<TagMembership>(`/${budgetId}/tags/${tagId}/membership`).then((r) => r.data),
    enabled: !!budgetId && !!tagId,
  })
}

/** Apply a checklist diff as one change — one Cmd+Z. */
export function useSetTagMembership(budgetId: string | null, tagId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (change: MembershipChange) =>
      apiClient
        .put<TagMembership>(`/${budgetId}/tags/${tagId}/categories`, change)
        .then((r) => r.data),
    onSuccess: () => invalidateAfterTagChange(qc, budgetId),
  })
}
