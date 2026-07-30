import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { FormatProvider } from './contexts/FormatContext'
import { MainLayout } from './components/layout/MainLayout/MainLayout'
import { OfflineBanner } from './components/pwa/OfflineBanner'
import { UpdateToast } from './components/pwa/UpdateToast'
import { useIsMobile } from './hooks/useMediaQuery'
import { useAppStore } from './stores/appStore'

// Pages are split per-route so the initial bundle stays lean — ReportsPage in
// particular pulls in recharts, which nothing else needs at first paint.
const LoginPage = lazy(() => import('./pages/LoginPage/LoginPage').then((m) => ({ default: m.LoginPage })))
const BudgetPage = lazy(() => import('./pages/BudgetPage/BudgetPage').then((m) => ({ default: m.BudgetPage })))
const BudgetSelectorPage = lazy(() => import('./pages/BudgetSelectorPage/BudgetSelectorPage').then((m) => ({ default: m.BudgetSelectorPage })))
const AccountPage = lazy(() => import('./pages/AccountPage/AccountPage').then((m) => ({ default: m.AccountPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const ImportPage = lazy(() => import('./pages/ImportPage/ImportPage').then((m) => ({ default: m.ImportPage })))
const ReportsPage = lazy(() => import('./pages/ReportsPage/ReportsPage').then((m) => ({ default: m.ReportsPage })))
const ScheduledTransactionsPage = lazy(() => import('./pages/ScheduledTransactionsPage/ScheduledTransactionsPage').then((m) => ({ default: m.ScheduledTransactionsPage })))
const PayeesPage = lazy(() => import('./pages/PayeesPage/PayeesPage').then((m) => ({ default: m.PayeesPage })))
const AccountsOverviewPage = lazy(() => import('./pages/AccountsOverviewPage/AccountsOverviewPage').then((m) => ({ default: m.AccountsOverviewPage })))
const LiabilitiesOverviewPage = lazy(() => import('./pages/LiabilitiesOverviewPage/LiabilitiesOverviewPage').then((m) => ({ default: m.LiabilitiesOverviewPage })))
const LiabilityPage = lazy(() => import('./pages/LiabilityPage/LiabilityPage').then((m) => ({ default: m.LiabilityPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Per-route Suspense keeps the layout shell (sidebar, header) visible while a
// page chunk loads instead of blanking the whole app.
function page(element: React.ReactNode) {
  return <Suspense fallback={null}>{element}</Suspense>
}

function ProtectedRoute() {
  const token = localStorage.getItem('access_token')
  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}

function BudgetRedirect() {
  const autoOpenLastBudget = useAppStore((s) => s.autoOpenLastBudget)
  const currentBudgetId = useAppStore((s) => s.currentBudgetId)
  if (autoOpenLastBudget && currentBudgetId) {
    return <Navigate to="/budget" replace />
  }
  return <Navigate to="/budgets" replace />
}

function AppToaster() {
  // Bottom is owned by the nav/selection bar/sheets on phones
  const isMobile = useIsMobile()
  return (
    <Toaster
      position={isMobile ? 'top-center' : 'bottom-right'}
      toastOptions={{
        duration: 4000,
        style: { fontSize: '13px', maxWidth: '400px' },
        ariaProps: { role: 'status', 'aria-live': 'polite' },
      }}
    />
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <FormatProvider>
        <AppToaster />
        <UpdateToast />
        <OfflineBanner />
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={page(<LoginPage />)} />
            <Route element={<ProtectedRoute />}>
              <Route path="/budgets" element={page(<BudgetSelectorPage />)} />
              <Route element={<MainLayout />}>
                <Route path="/budget" element={page(<BudgetPage />)} />
                <Route path="/accounts" element={page(<AccountsOverviewPage />)} />
                <Route path="/accounts/:accountId" element={page(<AccountPage />)} />
                <Route path="/liabilities" element={page(<LiabilitiesOverviewPage />)} />
                <Route path="/liabilities/:liabilityId" element={page(<LiabilityPage />)} />
                <Route path="/settings" element={page(<SettingsPage />)} />
                <Route path="/import" element={page(<ImportPage />)} />
                <Route path="/reports" element={page(<ReportsPage />)} />
                <Route path="/scheduled" element={page(<ScheduledTransactionsPage />)} />
                <Route path="/payees" element={page(<PayeesPage />)} />
              </Route>
              <Route index element={<BudgetRedirect />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </FormatProvider>
    </QueryClientProvider>
  )
}

export default App
