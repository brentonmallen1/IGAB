/**
 * Which row of reports the nav draws, and what starring does to it.
 *
 * Thirty reports sit behind a group dropdown and a row of tabs — good
 * for finding one you have never opened, poor for returning to the three you
 * read every week. Starred reports become a row of their own, reached from
 * the same dropdown as the groups.
 *
 * **A starred report keeps its real group.** Favourites is a way of looking at
 * the list, not a new home for a report: `getTabGroup` still answers Spending
 * for Cost of Living, and the nav's own state says whether the starred row is
 * the one on screen.
 *
 * **The starred row holds only while the active report is starred.** That one
 * rule replaces a pile of cleanup: unstarring the report you are looking at,
 * following a `?tab=` deep link, or arriving with a persisted flag from a
 * budget whose stars are gone all fall back to the report's own group with
 * nothing to reset.
 */
import {
  REPORT_TABS,
  TAB_GROUPS,
  getGroupTabs,
  getTabGroup,
  type ReportTab,
  type TabDef,
} from '../../stores/reportStore'

export const FAVORITES_LABEL = 'Favorites'

export interface ReportNav {
  /** The starred row rather than a group's row. */
  favorites: boolean
  /** What the dropdown trigger reads. */
  label: string
  /** The tabs to draw, in order. */
  tabs: TabDef[]
}

/** The starred ids as tabs, dropping any this build no longer has. */
export function favoriteTabs(favorites: readonly ReportTab[]): TabDef[] {
  return favorites
    .map((id) => REPORT_TABS.find((t) => t.id === id))
    .filter((t): t is TabDef => t !== undefined)
}

export function reportNav(
  activeTab: ReportTab,
  navFavorites: boolean,
  favorites: readonly ReportTab[]
): ReportNav {
  if (navFavorites && favorites.includes(activeTab)) {
    return { favorites: true, label: FAVORITES_LABEL, tabs: favoriteTabs(favorites) }
  }
  const group = getTabGroup(activeTab)
  return {
    favorites: false,
    label: TAB_GROUPS.find((g) => g.id === group)?.label ?? 'Reports',
    tabs: getGroupTabs(group),
  }
}

/**
 * Starring appends and unstarring removes, both preserving order.
 *
 * Appended rather than inserted in registry order, because the row is a list
 * the user built: the newest star arriving at the end keeps the positions
 * they have already learned to reach for.
 */
export function toggleFavorite(favorites: readonly ReportTab[], tab: ReportTab): ReportTab[] {
  return favorites.includes(tab) ? favorites.filter((f) => f !== tab) : [...favorites, tab]
}
