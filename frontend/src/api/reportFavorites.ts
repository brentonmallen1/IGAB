import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'
import { ROOT } from './queryKeys'
import type { ReportTab } from '../stores/reportStore'
import { liveReportTabs } from '../stores/reportStore'

interface FavoritesResponse {
  tabs: string[]
}

/**
 * The starred reports, as report ids this build knows about.
 *
 * The server stores the list and does not interpret it — which reports exist
 * is a client fact (see `services/report_favorites.py`), so the reading here
 * is the other half of that bargain (`liveReportTabs`): a star on a report
 * that has since been merged into another stars its successor, and one on a
 * report that is simply gone drops out of the row rather than drawing a tab
 * that cannot be rendered. The next star toggled writes the row as it reads.
 */
export function useReportFavorites(budgetId: string | null) {
  return useQuery({
    queryKey: [ROOT.reportFavorites, budgetId],
    queryFn: async () => {
      const { data } = await apiClient.get<FavoritesResponse>(`/${budgetId}/reports/favorites`)
      return liveReportTabs(data.tabs)
    },
    enabled: !!budgetId,
    staleTime: 60_000,
  })
}

/**
 * Writes the whole list, not a delta: a star is a toggle on a short list, and
 * a PUT of the result cannot disagree with itself the way an add/remove pair
 * can when two tabs are open.
 */
export function useSetReportFavorites(budgetId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tabs: ReportTab[]) => {
      const { data } = await apiClient.put<FavoritesResponse>(`/${budgetId}/reports/favorites`, {
        tabs,
      })
      return data.tabs
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ROOT.reportFavorites, budgetId] })
    },
  })
}
