import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { syncThemeColorMeta } from '../utils/themeColor'

export type Theme = 'dark' | 'light' | 'gruvbox-dark' | 'gruvbox-light' | 'catppuccin-mocha' | 'catppuccin-latte' | 'rose-pine' | 'rose-pine-moon' | 'nord'

interface AppState {
  theme: Theme
  currentBudgetId: string | null
  selectedAccountId: string | null
  selectedMonth: string // ISO date string: "2024-01-01"
  autoOpenLastBudget: boolean
  lastQuickAddAccountId: string | null
  /** Opt-in, device-local: capture location on quick-add to suggest nearby payees */
  locationEnabled: boolean

  setTheme: (theme: Theme) => void
  setCurrentBudgetId: (id: string) => void
  clearCurrentBudget: () => void
  setSelectedAccountId: (id: string | null) => void
  setSelectedMonth: (month: string) => void
  setAutoOpenLastBudget: (val: boolean) => void
  setLastQuickAddAccountId: (id: string) => void
  setLocationEnabled: (val: boolean) => void
}

function currentMonthString(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'dark',
      currentBudgetId: null,
      selectedAccountId: null,
      selectedMonth: currentMonthString(),
      autoOpenLastBudget: true,
      lastQuickAddAccountId: null,
      locationEnabled: false,

      setTheme: (theme) => {
        document.documentElement.setAttribute('data-theme', theme)
        syncThemeColorMeta()
        set({ theme })
      },
      setCurrentBudgetId: (id) => set({ currentBudgetId: id, selectedAccountId: null }),
      clearCurrentBudget: () => set({ currentBudgetId: null, selectedAccountId: null }),
      setSelectedAccountId: (id) => set({ selectedAccountId: id }),
      setSelectedMonth: (month) => set({ selectedMonth: month }),
      setAutoOpenLastBudget: (val) => set({ autoOpenLastBudget: val }),
      setLastQuickAddAccountId: (id) => set({ lastQuickAddAccountId: id }),
      setLocationEnabled: (val) => set({ locationEnabled: val }),
    }),
    {
      name: 'igab-app',
      onRehydrateStorage: () => (state) => {
        // Apply theme on hydration
        if (state?.theme) {
          document.documentElement.setAttribute('data-theme', state.theme)
        }
        syncThemeColorMeta()
      },
    }
  )
)
