import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useBudgets } from '../../../api/budgets'
import { Sidebar } from '../Sidebar/Sidebar'
import { Header } from '../Header/Header'
import { OfflineBanner } from '../../pwa/OfflineBanner'
import { BottomNav } from '../BottomNav/BottomNav'
import { MoreSheet } from '../MoreSheet/MoreSheet'
import { QuickAddSheet } from '../../transactions/QuickAddSheet/QuickAddSheet'
import { CommandPalette } from '../../palette/CommandPalette/CommandPalette'
import { GlobalShortcuts } from '../GlobalShortcuts'
import { useAppStore } from '../../../stores/appStore'
import './MainLayout.css'

export function MainLayout() {
  const theme = useAppStore((s) => s.theme)
  const currentBudgetId = useAppStore((s) => s.currentBudgetId)
  const clearCurrentBudget = useAppStore((s) => s.clearCurrentBudget)
  const { data: budgets, isSuccess, isFetching } = useBudgets()
  // A persisted budget id can outlive the budget itself (deleted budget,
  // recreated database). Without this check every page renders empty with
  // no way back to the selector. The !isFetching guard keeps a mid-refetch
  // cached list (isSuccess stays true) from condemning a just-created budget
  // that only the in-flight response knows about.
  const staleBudget =
    currentBudgetId !== null &&
    isSuccess &&
    !isFetching &&
    !budgets.some((b) => b.id === currentBudgetId)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    if (staleBudget) clearCurrentBudget()
  }, [staleBudget, clearCurrentBudget])

  if (!currentBudgetId || staleBudget) {
    return <Navigate to="/budgets" replace />
  }

  return (
    <div className="main-layout">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Sidebar />
      <div className="main-layout__content">
        <OfflineBanner />
        <Header />
        <main id="main-content" className="main-layout__main">
          <Outlet />
        </main>
        {/* In flow as the last row of the content column, not position:fixed.
            A fixed nav is anchored to the layout viewport, which iOS slides out
            from under the visible area when the keyboard opens — and it can
            paint over any overlay that ranks below it. In flow, neither is
            possible by construction. */}
        <BottomNav />
      </div>
      <MoreSheet />
      <QuickAddSheet />
      <CommandPalette />
      <GlobalShortcuts />
    </div>
  )
}
