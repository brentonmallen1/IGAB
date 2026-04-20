import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'dark' | 'light' | 'gruvbox-dark' | 'gruvbox-light' | 'catppuccin-mocha' | 'catppuccin-latte' | 'rose-pine' | 'rose-pine-moon' | 'nord'

interface AppState {
  theme: Theme
  currentBudgetId: string | null
  selectedAccountId: string | null
  selectedMonth: string // ISO date string: "2024-01-01"
  autoOpenLastBudget: boolean

  setTheme: (theme: Theme) => void
  setCurrentBudgetId: (id: string) => void
  clearCurrentBudget: () => void
  setSelectedAccountId: (id: string | null) => void
  setSelectedMonth: (month: string) => void
  setAutoOpenLastBudget: (val: boolean) => void
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

      setTheme: (theme) => {
        document.documentElement.setAttribute('data-theme', theme)
        set({ theme })
      },
      setCurrentBudgetId: (id) => set({ currentBudgetId: id, selectedAccountId: null }),
      clearCurrentBudget: () => set({ currentBudgetId: null, selectedAccountId: null }),
      setSelectedAccountId: (id) => set({ selectedAccountId: id }),
      setSelectedMonth: (month) => set({ selectedMonth: month }),
      setAutoOpenLastBudget: (val) => set({ autoOpenLastBudget: val }),
    }),
    {
      name: 'igab-app',
      onRehydrateStorage: () => (state) => {
        // Apply theme on hydration
        if (state?.theme) {
          document.documentElement.setAttribute('data-theme', state.theme)
        }
      },
    }
  )
)
