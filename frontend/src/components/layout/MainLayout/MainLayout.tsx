import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useBudgets } from '../../../api/budgets'
import { Sidebar } from '../Sidebar/Sidebar'
import { Header } from '../Header/Header'
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
  const { data: budgets, isSuccess } = useBudgets()
  // A persisted budget id can outlive the budget itself (deleted budget,
  // recreated database). Without this check every page renders empty with
  // no way back to the selector.
  const staleBudget =
    currentBudgetId !== null && isSuccess && !budgets.some((b) => b.id === currentBudgetId)

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
        <Header />
        <main id="main-content" className="main-layout__main">
          <Outlet />
        </main>
      </div>
      <BottomNav />
      <MoreSheet />
      <QuickAddSheet />
      <CommandPalette />
      <GlobalShortcuts />
    </div>
  )
}
