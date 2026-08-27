import { lazy, Suspense } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { FormatProvider } from './contexts/FormatContext'
import { MainLayout } from './components/layout/MainLayout/MainLayout'
import { UpdateToast } from './components/pwa/UpdateToast'
import { useIsMobile } from './hooks/useMediaQuery'
import { useAppViewport } from './hooks/useAppViewport'
import { ConfirmHost } from './components/common/ConfirmSheet/ConfirmHost'
import { useAppStore } from './stores/appStore'

// Pages are split per-route so the initial bundle stays lean — ReportsPage in
// particular pulls in recharts, which nothing else needs at first paint.
const LoginPage = lazy(() => import('./pages/LoginPage/LoginPage').then((m) => ({ default: m.LoginPage })))
const BudgetPage = lazy(() => import('./pages/BudgetPage/BudgetPage').then((m) => ({ default: m.BudgetPage })))
const BudgetSelectorPage = lazy(() => import('./pages/BudgetSelectorPage/BudgetSelectorPage').then((m) => ({ default: m.BudgetSelectorPage })))
const AccountPage = lazy(() => import('./pages/AccountPage/AccountPage').then((m) => ({ default: m.AccountPage })))
const AllTransactionsPage = lazy(() => import('./pages/AllTransactionsPage/AllTransactionsPage').then((m) => ({ default: m.AllTransactionsPage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const ImportPage = lazy(() => import('./pages/ImportPage/ImportPage').then((m) => ({ default: m.ImportPage })))
const ReportsPage = lazy(() => import('./pages/ReportsPage/ReportsPage').then((m) => ({ default: m.ReportsPage })))
const ScheduledTransactionsPage = lazy(() => import('./pages/ScheduledTransactionsPage/ScheduledTransactionsPage').then((m) => ({ default: m.ScheduledTransactionsPage })))
const PayeesPage = lazy(() => import('./pages/PayeesPage/PayeesPage').then((m) => ({ default: m.PayeesPage })))
const AccountsOverviewPage = lazy(() => import('./pages/AccountsOverviewPage/AccountsOverviewPage').then((m) => ({ default: m.AccountsOverviewPage })))
const AIActivityPage = lazy(() => import('./pages/AIActivityPage/AIActivityPage').then((m) => ({ default: m.AIActivityPage })))
const ActivityPage = lazy(() => import('./pages/ActivityPage/ActivityPage').then((m) => ({ default: m.ActivityPage })))
const LiabilitiesOverviewPage = lazy(() => import('./pages/LiabilitiesOverviewPage/LiabilitiesOverviewPage').then((m) => ({ default: m.LiabilitiesOverviewPage })))
const GuidePage = lazy(() => import('./pages/GuidePage/GuidePage').then((m) => ({ default: m.GuidePage })))
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
      containerStyle={{
        // react-hot-toast hardcodes z-index 9999; bring it onto the app's
        // ladder so it clears modals without outranking the skip link.
        zIndex: 'var(--z-toast)',
        // Its default is a flat 16px inset. In a standalone PWA the status bar
        // and Dynamic Island overlay the top of the viewport, and iOS routes
        // taps there to scroll-to-top — so a top-center toast rendered under
        // them is visible but impossible to press. --vv-top additionally keeps
        // it on the visible viewport when the keyboard shifts things.
        top: 'calc(var(--vv-top) + var(--safe-top) + var(--spacing-sm))',
        bottom: 'calc(var(--nav-h) + var(--safe-bottom) + var(--spacing-sm))',
        left: 'calc(var(--safe-left) + var(--spacing-sm))',
        right: 'calc(var(--safe-right) + var(--spacing-sm))',
      }}
      toastOptions={{
        duration: 4000,
        style: {
          fontSize: '13px',
          maxWidth: 'min(400px, calc(100vw - 32px))',
          // react-hot-toast's default is a white card with dark text — a
          // stranger in every dark palette, and the update prompt painted its
          // own themed text onto it. Toasts are overlays; paint them as one.
          background: 'var(--surface-overlay)',
          color: 'var(--text-primary)',
          border: '1px solid var(--edge)',
          boxShadow: 'var(--elevation-overlay)',
        },
        ariaProps: { role: 'status', 'aria-live': 'polite' },
      }}
    />
  )
}

function App() {
  // Single source of viewport truth for the whole app. Mounted here rather
  // than in MainLayout because LoginPage and BudgetSelectorPage render
  // outside it and size themselves against the same tokens.
  useAppViewport()
  return (
    <QueryClientProvider client={queryClient}>
      <FormatProvider>
        <AppToaster />
        <UpdateToast />
        {/* Above the router: LoginPage and BudgetSelectorPage render outside
            MainLayout, and confirmAsync() must resolve for them too — an
            unrendered host leaves the caller awaiting forever. */}
        <ConfirmHost />
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={page(<LoginPage />)} />
            <Route element={<ProtectedRoute />}>
              <Route path="/budgets" element={page(<BudgetSelectorPage />)} />
              <Route element={<MainLayout />}>
                <Route path="/budget" element={page(<BudgetPage />)} />
                <Route path="/accounts" element={page(<AccountsOverviewPage />)} />
                <Route path="/accounts/:accountId" element={page(<AccountPage />)} />
                <Route path="/transactions" element={page(<AllTransactionsPage />)} />
                <Route path="/liabilities" element={page(<LiabilitiesOverviewPage />)} />
                <Route path="/liabilities/:liabilityId" element={page(<LiabilityPage />)} />
                <Route path="/settings" element={page(<SettingsPage />)} />
                <Route path="/import" element={page(<ImportPage />)} />
                <Route path="/reports" element={page(<ReportsPage />)} />
                <Route path="/guide" element={page(<GuidePage />)} />
                <Route path="/scheduled" element={page(<ScheduledTransactionsPage />)} />
                <Route path="/payees" element={page(<PayeesPage />)} />
                <Route path="/ai-activity" element={page(<AIActivityPage />)} />
                <Route path="/activity" element={page(<ActivityPage />)} />
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
