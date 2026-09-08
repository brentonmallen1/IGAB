/**
 * Where "back" goes from a page, for the surfaces that need to know without
 * a browser history to ask: the shell's edge-swipe (the installed PWA has no
 * back gesture) and a page header's back chevron. One map, so the two agree.
 *
 * Drill-in pages return to their list; everything else returns to the
 * budget, which is where the bottom nav starts.
 */
export function parentRoute(pathname: string): string {
  const drillIn = pathname.match(/^\/(accounts|liabilities|assets)\/[^/]+/)
  if (drillIn) return `/${drillIn[1]}`
  if (pathname === '/system') return '/settings'
  if (pathname === '/budget' || pathname === '/') return '/budget'
  return '/budget'
}
