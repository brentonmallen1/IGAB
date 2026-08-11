import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { syncThemeColorMeta } from '../utils/themeColor'

export type Theme = 'dark' | 'light' | 'gruvbox-dark' | 'gruvbox-light' | 'catppuccin-mocha' | 'catppuccin-latte' | 'rose-pine' | 'rose-pine-moon' | 'nord' | 'nineties-dark' | 'nineties-light' | 'eighties-dark' | 'eighties-light' | 'eighties-pop-dark' | 'eighties-pop-light' | 'synthwave-dark' | 'synthwave-light' | 'cozy-dark' | 'cozy-light' | 'vapor-dark' | 'vapor-light' | 'kodachrome-dark' | 'kodachrome-light' | 'phosphor-dark' | 'phosphor-light' | 'blueprint-dark' | 'blueprint-light' | 'desert-dark' | 'desert-light' | 'bauhaus-dark' | 'bauhaus-light' | 'paper-dark' | 'paper-light' | 'eink-dark' | 'eink-light'

export interface Palette {
  id: string
  label: string
  dark: Theme
  light: Theme
}

export const PALETTES: Palette[] = [
  { id: 'default', label: 'Default', dark: 'dark', light: 'light' },
  { id: 'gruvbox', label: 'Gruvbox', dark: 'gruvbox-dark', light: 'gruvbox-light' },
  { id: 'catppuccin', label: 'Catppuccin', dark: 'catppuccin-mocha', light: 'catppuccin-latte' },
  { id: 'rose-pine', label: 'Rosé Pine', dark: 'rose-pine-moon', light: 'rose-pine' },
  { id: 'nord', label: 'Nord', dark: 'nord', light: 'nord' },
  { id: 'nineties', label: "90's", dark: 'nineties-dark', light: 'nineties-light' },
  { id: 'eighties', label: "80's", dark: 'eighties-dark', light: 'eighties-light' },
  { id: 'eighties-pop', label: "80's Pop", dark: 'eighties-pop-dark', light: 'eighties-pop-light' },
  { id: 'synthwave', label: 'Synthwave', dark: 'synthwave-dark', light: 'synthwave-light' },
  { id: 'cozy', label: 'Cozy', dark: 'cozy-dark', light: 'cozy-light' },
  { id: 'vapor', label: 'Vapor', dark: 'vapor-dark', light: 'vapor-light' },
  { id: 'kodachrome', label: 'Kodachrome', dark: 'kodachrome-dark', light: 'kodachrome-light' },
  { id: 'phosphor', label: 'Phosphor', dark: 'phosphor-dark', light: 'phosphor-light' },
  { id: 'blueprint', label: 'Blueprint', dark: 'blueprint-dark', light: 'blueprint-light' },
  { id: 'desert', label: 'Desert', dark: 'desert-dark', light: 'desert-light' },
  { id: 'bauhaus', label: 'Bauhaus', dark: 'bauhaus-dark', light: 'bauhaus-light' },
  { id: 'paper', label: 'Paper', dark: 'paper-dark', light: 'paper-light' },
  { id: 'eink', label: 'E-Ink', dark: 'eink-dark', light: 'eink-light' },
]

export function getPaletteForTheme(theme: Theme): Palette {
  return PALETTES.find((p) => p.dark === theme || p.light === theme) ?? PALETTES[0]
}

export function isLightTheme(theme: Theme): boolean {
  const palette = getPaletteForTheme(theme)
  return theme === palette.light
}

export const THEMES: { value: Theme; label: string }[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'gruvbox-dark', label: 'Gruvbox Dark' },
  { value: 'gruvbox-light', label: 'Gruvbox Light' },
  { value: 'catppuccin-mocha', label: 'Catppuccin Mocha' },
  { value: 'catppuccin-latte', label: 'Catppuccin Latte' },
  { value: 'rose-pine', label: 'Rosé Pine' },
  { value: 'rose-pine-moon', label: 'Rosé Pine Moon' },
  { value: 'nord', label: 'Nord' },
  { value: 'nineties-dark', label: "90's Dark" },
  { value: 'nineties-light', label: "90's Light" },
  { value: 'eighties-dark', label: "80's Dark" },
  { value: 'eighties-light', label: "80's Light" },
  { value: 'eighties-pop-dark', label: "80's Pop Dark" },
  { value: 'eighties-pop-light', label: "80's Pop Light" },
  { value: 'synthwave-dark', label: 'Synthwave Dark' },
  { value: 'synthwave-light', label: 'Synthwave Light' },
  { value: 'cozy-dark', label: 'Cozy Dark' },
  { value: 'cozy-light', label: 'Cozy Light' },
  { value: 'vapor-dark', label: 'Vapor Dark' },
  { value: 'vapor-light', label: 'Vapor Light' },
  { value: 'kodachrome-dark', label: 'Kodachrome Dark' },
  { value: 'kodachrome-light', label: 'Kodachrome Light' },
  { value: 'phosphor-dark', label: 'Phosphor Green' },
  { value: 'phosphor-light', label: 'Phosphor Amber' },
  { value: 'blueprint-dark', label: 'Blueprint Dark' },
  { value: 'blueprint-light', label: 'Blueprint Light' },
  { value: 'desert-dark', label: 'Desert Dark' },
  { value: 'desert-light', label: 'Desert Light' },
  { value: 'bauhaus-dark', label: 'Bauhaus Dark' },
  { value: 'bauhaus-light', label: 'Bauhaus Light' },
  { value: 'paper-dark', label: 'Paper Dark' },
  { value: 'paper-light', label: 'Paper Light' },
  { value: 'eink-dark', label: 'E-Ink Dark' },
  { value: 'eink-light', label: 'E-Ink Light' },
]

export type FontScale = 'small' | 'medium' | 'large'

export const FONT_SCALES: { value: FontScale; label: string }[] = [
  { value: 'small', label: 'Small' },
  { value: 'medium', label: 'Medium' },
  { value: 'large', label: 'Large' },
]

interface AppState {
  theme: Theme
  fontScale: FontScale
  currentBudgetId: string | null
  selectedAccountId: string | null
  selectedMonth: string // ISO date string: "2024-01-01"
  autoOpenLastBudget: boolean
  lastQuickAddAccountId: string | null
  /** Opt-in, device-local: capture location on quick-add to suggest nearby payees */
  locationEnabled: boolean
  /** Device-local: mask all amounts (screen-share / over-the-shoulder privacy) */
  privacyMode: boolean

  setTheme: (theme: Theme) => void
  setFontScale: (scale: FontScale) => void
  setCurrentBudgetId: (id: string) => void
  clearCurrentBudget: () => void
  setSelectedAccountId: (id: string | null) => void
  setSelectedMonth: (month: string) => void
  setAutoOpenLastBudget: (val: boolean) => void
  setLastQuickAddAccountId: (id: string) => void
  setLocationEnabled: (val: boolean) => void
  togglePrivacyMode: () => void
}

function currentMonthString(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'dark',
      fontScale: 'small',
      currentBudgetId: null,
      selectedAccountId: null,
      selectedMonth: currentMonthString(),
      autoOpenLastBudget: true,
      lastQuickAddAccountId: null,
      locationEnabled: false,
      privacyMode: false,

      setTheme: (theme) => {
        document.documentElement.setAttribute('data-theme', theme)
        syncThemeColorMeta()
        set({ theme })
      },
      setFontScale: (scale) => {
        document.documentElement.setAttribute('data-font-size', scale)
        set({ fontScale: scale })
      },
      setCurrentBudgetId: (id) => set({ currentBudgetId: id, selectedAccountId: null }),
      clearCurrentBudget: () => set({ currentBudgetId: null, selectedAccountId: null }),
      setSelectedAccountId: (id) => set({ selectedAccountId: id }),
      setSelectedMonth: (month) => set({ selectedMonth: month }),
      setAutoOpenLastBudget: (val) => set({ autoOpenLastBudget: val }),
      setLastQuickAddAccountId: (id) => set({ lastQuickAddAccountId: id }),
      setLocationEnabled: (val) => set({ locationEnabled: val }),
      togglePrivacyMode: () => set((s) => ({ privacyMode: !s.privacyMode })),
    }),
    {
      name: 'igab-app',
      onRehydrateStorage: () => (state) => {
        // Apply theme and font scale on hydration
        if (state?.theme) {
          document.documentElement.setAttribute('data-theme', state.theme)
        }
        if (state?.fontScale) {
          document.documentElement.setAttribute('data-font-size', state.fontScale)
        }
        syncThemeColorMeta()
      },
    }
  )
)
