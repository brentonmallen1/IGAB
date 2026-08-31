import type { LucideIcon } from 'lucide-react'
import {
  ArrowLeftRight,
  Calculator,
  ArrowRightLeft,
  BarChart3,
  EyeOff,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Compass,
  Landmark,
  LifeBuoy,
  Plus,
  RefreshCw,
  Settings,
  Upload,
  Users,
  Wallet,
  Wand2,
} from 'lucide-react'
import { REPORT_TABS, TAB_GROUPS } from '../../stores/reportStore'
import { GUIDE_TABS } from '../../stores/guideStore'
import { TOOLS } from '../guide/tools/toolRegistry'
import { visibleSettingsSections } from '../../pages/SettingsPage/settingsSections'

/** Everything a command may do, injected by the palette so commands stay pure */
export interface CommandCtx {
  navigate: (to: string) => void
  openQuickAdd: () => void
  openAutoAssign: () => void
  openCoverOverspent: () => void
  openTbaDrawer: () => void
  /** 1 = next month, -1 = previous, 0 = jump to current */
  goMonth: (delta: 1 | -1 | 0) => void
  togglePrivacy: () => void
  /** Sync every linked bank connection. No-op with none linked. */
  syncAll: () => void
}

export interface AppCommand {
  id: string
  label: string
  section: 'Actions' | 'Navigate' | 'Tools'
  /** Extra match terms beyond the label */
  keywords?: string
  icon: LucideIcon
  run: (ctx: CommandCtx) => void
}

export const STATIC_COMMANDS: AppCommand[] = [
  // ── Actions ──
  {
    id: 'add-transaction',
    label: 'Add transaction',
    section: 'Actions',
    keywords: 'new create quick entry',
    icon: Plus,
    run: (c) => c.openQuickAdd(),
  },
  {
    id: 'sync-all',
    label: 'Sync all accounts',
    section: 'Actions',
    keywords: 'bank simplefin refresh fetch download transactions',
    icon: RefreshCw,
    run: (c) => c.syncAll(),
  },
  {
    id: 'auto-assign',
    label: 'Auto-assign to targets',
    section: 'Actions',
    keywords: 'fill fund budget distribute',
    icon: Wand2,
    run: (c) => {
      c.navigate('/budget')
      c.openAutoAssign()
    },
  },
  {
    id: 'cover-overspent',
    label: 'Cover overspending',
    section: 'Actions',
    keywords: 'overspent red fix negative',
    icon: LifeBuoy,
    run: (c) => {
      c.navigate('/budget')
      c.openCoverOverspent()
    },
  },
  {
    id: 'move-money',
    label: 'Move money',
    section: 'Actions',
    keywords: 'transfer envelope shift funds',
    icon: ArrowRightLeft,
    run: (c) => {
      c.navigate('/budget')
      c.openTbaDrawer()
    },
  },
  {
    id: 'month-next',
    label: 'Go to next month',
    section: 'Actions',
    keywords: 'forward',
    icon: ChevronRight,
    run: (c) => c.goMonth(1),
  },
  {
    id: 'month-prev',
    label: 'Go to previous month',
    section: 'Actions',
    keywords: 'back last',
    icon: ChevronLeft,
    run: (c) => c.goMonth(-1),
  },
  {
    id: 'month-today',
    label: 'Jump to current month',
    section: 'Actions',
    keywords: 'today now',
    icon: CalendarDays,
    run: (c) => c.goMonth(0),
  },

  // ── Navigate ──
  {
    id: 'nav-budget',
    label: 'Budget',
    section: 'Navigate',
    icon: Wallet,
    run: (c) => c.navigate('/budget'),
  },
  {
    id: 'nav-accounts',
    label: 'All accounts',
    section: 'Navigate',
    icon: Landmark,
    run: (c) => c.navigate('/accounts'),
  },
  {
    id: 'nav-reports',
    label: 'Reports',
    section: 'Navigate',
    keywords: 'charts analytics',
    icon: BarChart3,
    run: (c) => c.navigate('/reports'),
  },
  {
    id: 'nav-guide',
    label: 'Guide',
    section: 'Navigate',
    keywords: 'roadmap education glossary learn help checkup wishlist',
    icon: Compass,
    run: (c) => c.navigate('/guide'),
  },
  {
    id: 'nav-scheduled',
    label: 'Scheduled transactions',
    section: 'Navigate',
    keywords: 'recurring repeating',
    icon: CalendarClock,
    run: (c) => c.navigate('/scheduled'),
  },
  {
    id: 'nav-payees',
    label: 'Payees',
    section: 'Navigate',
    keywords: 'merchants',
    icon: Users,
    run: (c) => c.navigate('/payees'),
  },
  {
    id: 'nav-import',
    label: 'Import transactions',
    section: 'Navigate',
    keywords: 'csv upload',
    icon: Upload,
    run: (c) => c.navigate('/import'),
  },
  {
    id: 'nav-settings',
    label: 'Settings',
    section: 'Navigate',
    keywords: 'preferences options',
    icon: Settings,
    run: (c) => c.navigate('/settings'),
  },
  {
    id: 'nav-switch-budget',
    label: 'Switch budget…',
    section: 'Navigate',
    keywords: 'change select',
    icon: ArrowLeftRight,
    run: (c) => c.navigate('/budgets'),
  },

  // ── Tools ──
  {
    id: 'tool-privacy',
    label: 'Toggle privacy mode',
    section: 'Tools',
    keywords: 'mask hide amounts blur screen share',
    icon: EyeOff,
    run: (c) => c.togglePrivacy(),
  },
]

/**
 * Rows the palette derives rather than a person writing them.
 *
 * Every destination below was already addressable — `/reports?tab=`,
 * `/guide?tab=&tool=`, `/settings#section` all exist and are validated on
 * arrival. The only thing missing was a way to type its name. Generating the
 * rows from the same registries the pages render from means a new report tab
 * is reachable the day it lands, and a renamed one cannot leave a palette row
 * pointing at nothing.
 *
 * Each row carries its group in the label (`Report: Net Worth`) because 23
 * reports in one flat list is a wall, and in its keywords (`Spending`) so
 * typing a group name surfaces everything under it.
 *
 * These appear only once something is typed. Opening the palette onto 40-odd
 * generated rows would bury the twenty commands it exists to offer — the same
 * reason the glossary group stays quiet on an empty query.
 */

/** The gates the palette must apply, because it offers the same destinations
 *  the pages do. Passed in rather than read here so this stays pure. */
export interface DerivedCommandCtx {
  budgetId: string | null
  isAdmin: boolean
  /** Guide tabs switched off in preferences. Offering one would navigate to a
   *  tab GuidePage does not render — and it bounces to Roadmap. */
  hiddenGuideTabs: readonly string[]
}

export function reportCommands(): AppCommand[] {
  return REPORT_TABS.map((tab) => ({
    id: `report-${tab.id}`,
    label: `Report: ${tab.label}`,
    section: 'Navigate' as const,
    keywords: `report ${TAB_GROUPS.find((g) => g.id === tab.group)?.label ?? ''}`,
    icon: BarChart3,
    run: (c: CommandCtx) => c.navigate(`/reports?tab=${tab.id}`),
  }))
}

export function guideCommands(ctx: DerivedCommandCtx): AppCommand[] {
  const tabs: AppCommand[] = GUIDE_TABS.filter((tab) => !ctx.hiddenGuideTabs.includes(tab.id)).map(
    (tab) => ({
      id: `guide-${tab.id}`,
      label: `Guide: ${tab.label}`,
      section: 'Navigate' as const,
      keywords: 'guide roadmap',
      icon: Compass,
      run: (c: CommandCtx) => c.navigate(`/guide?tab=${tab.id}`),
    })
  )
  const tools: AppCommand[] = Object.values(TOOLS).map((tool) => ({
    id: `calc-${tool.id}`,
    label: `Calculator: ${tool.label}`,
    section: 'Tools' as const,
    keywords: 'guide calculator tool',
    icon: Calculator,
    run: (c: CommandCtx) => c.navigate(`/guide?tab=tools&tool=${tool.id}`),
  }))
  return [...tabs, ...tools]
}

export function settingsCommands(ctx: DerivedCommandCtx): AppCommand[] {
  return visibleSettingsSections({ budgetId: ctx.budgetId, isAdmin: ctx.isAdmin }).map(
    (section) => ({
      id: `settings-${section.id}`,
      label: `Settings: ${section.label}`,
      section: 'Navigate' as const,
      keywords: `settings preferences ${section.keywords ?? ''}`,
      icon: Settings,
      run: (c: CommandCtx) => c.navigate(`/settings#${section.id}`),
    })
  )
}

/** Every derived row, gated. One call, so a caller cannot pick up the reports
 *  and quietly forget the gates on the rest. */
export function derivedCommands(ctx: DerivedCommandCtx): AppCommand[] {
  return [...reportCommands(), ...guideCommands(ctx), ...settingsCommands(ctx)]
}
