import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import type { SignalKey } from '../content/roadmap'

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
    queryKey: ['guide', budgetId],
    queryFn: () => apiClient.get<GuideOverview>(`/${budgetId}/guide`).then((r) => r.data),
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

export function useGuideSignals(budgetId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['guide-signals', budgetId],
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
    queryKey: ['guide-candidates', budgetId, conceptKey],
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['guide-signals', budgetId] }),
  })
}

export function useSetGuidePreferences(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (changes: Partial<GuidePreferences>) =>
      apiClient
        .put<GuidePreferences>(`/${budgetId}/guide/preferences`, changes)
        .then((r) => r.data),
    onSuccess: (prefs) => {
      // Seed rather than only invalidate: the toggle should settle instantly,
      // and the server may have forced checkup off alongside personalisation.
      qc.setQueryData<GuideOverview | undefined>(['guide', budgetId], (old) =>
        old ? { ...old, preferences: prefs } : old
      )
      qc.invalidateQueries({ queryKey: ['guide', budgetId] })
      qc.invalidateQueries({ queryKey: ['guide-signals', budgetId] })
    },
  })
}

export function useSetGuideStep(budgetId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ stageId, state }: { stageId: string; state: 'done' | 'skipped' | null }) =>
      apiClient.put(`/${budgetId}/guide/progress/${stageId}`, { state }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['guide', budgetId] }),
  })
}
