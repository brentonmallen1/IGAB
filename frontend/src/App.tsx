import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { MainLayout } from './components/layout/MainLayout/MainLayout'
import { LoginPage } from './pages/LoginPage/LoginPage'
import { BudgetPage } from './pages/BudgetPage/BudgetPage'
import { BudgetSelectorPage } from './pages/BudgetSelectorPage/BudgetSelectorPage'
import { AccountPage } from './pages/AccountPage/AccountPage'
import { SettingsPage } from './pages/SettingsPage/SettingsPage'
import { ImportPage } from './pages/ImportPage/ImportPage'
import { ReportsPage } from './pages/ReportsPage/ReportsPage'
import { ScheduledTransactionsPage } from './pages/ScheduledTransactionsPage/ScheduledTransactionsPage'
import { PayeesPage } from './pages/PayeesPage/PayeesPage'
import { AccountsOverviewPage } from './pages/AccountsOverviewPage/AccountsOverviewPage'
import { useAppStore } from './stores/appStore'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

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

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 4000,
          style: { fontSize: '13px', maxWidth: '400px' },
        }}
      />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/budgets" element={<BudgetSelectorPage />} />
            <Route element={<MainLayout />}>
              <Route path="/budget" element={<BudgetPage />} />
              <Route path="/accounts" element={<AccountsOverviewPage />} />
              <Route path="/accounts/:accountId" element={<AccountPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/scheduled" element={<ScheduledTransactionsPage />} />
              <Route path="/payees" element={<PayeesPage />} />
            </Route>
            <Route index element={<BudgetRedirect />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
