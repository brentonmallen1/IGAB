import type { LucideIcon } from 'lucide-react'
import {
  ArrowLeftRight,
  ArrowRightLeft,
  BarChart3,
  EyeOff,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Compass,
  DatabaseBackup,
  Landmark,
  LifeBuoy,
  Plus,
  RefreshCw,
  Settings,
  ShieldCheck,
  Upload,
  Users,
  Wallet,
  Wand2,
} from 'lucide-react'

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
  {
    id: 'tool-integrity',
    label: 'Run integrity check',
    section: 'Tools',
    keywords: 'database health verify audit',
    icon: ShieldCheck,
    run: (c) => c.navigate('/settings#integrity'),
  },
  {
    id: 'tool-backups',
    label: 'Backups',
    section: 'Tools',
    keywords: 'export restore data dump',
    icon: DatabaseBackup,
    run: (c) => c.navigate('/settings#data'),
  },
]
