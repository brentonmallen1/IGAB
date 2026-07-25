import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Landmark, Palette as PaletteIcon, Receipt, Search, User, Bookmark } from 'lucide-react'
import { apiClient } from '../../../api/client'
import { useAccounts } from '../../../api/accounts'
import { usePayees } from '../../../api/payees'
import { useBudgetViews } from '../../../api/budgetViews'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useShortcut } from '../../../hooks/useShortcut'
import { addMonths, currentMonthStart, formatDate } from '../../../utils/dates'
import { formatMoney } from '../../../utils/money'
import { THEMES } from '../../layout/Header/Header'
import { STATIC_COMMANDS, type CommandCtx } from '../commands'
import type { BudgetTransactionsResponse } from '../../../types'
import './CommandPalette.css'

/**
 * ⌘K command palette: navigation, budget actions, theme switching, and live
 * payee/transaction search. Desktop-only — mobile has the bottom nav and
 * quick-add sheet.
 */
export function CommandPalette() {
  const isMobile = useIsMobile()
  const navigate = useNavigate()

  const open = useUIStore((s) => s.isPaletteOpen)
  const closePalette = useUIStore((s) => s.closePalette)
  const togglePalette = useUIStore((s) => s.togglePalette)
  const openQuickAdd = useUIStore((s) => s.openQuickAdd)
  const setAutoAssignOpen = useUIStore((s) => s.setAutoAssignOpen)
  const setCoverOverspentOpen = useUIStore((s) => s.setCoverOverspentOpen)
  const setTbaDrawerOpen = useUIStore((s) => s.setTbaDrawerOpen)
  const setActiveBudgetView = useUIStore((s) => s.setActiveBudgetView)

  const budgetId = useAppStore((s) => s.currentBudgetId)
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)

  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')

  useShortcut('mod+k', () => togglePalette(), { allowInInputs: true, enabled: !isMobile })

  useEffect(() => {
    if (!open) {
      setQuery('')
      setDebounced('')
    }
  }, [open])

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 250)
    return () => clearTimeout(t)
  }, [query])

  const { data: accounts = [] } = useAccounts(open ? budgetId : null)
  const { data: payees = [] } = usePayees(open ? budgetId : null)
  const { data: views = [] } = useBudgetViews(open ? budgetId : null)

  const searchTerm = debounced.trim()
  const searchOn = open && !!budgetId && searchTerm.length >= 2

  const { data: txnResults } = useQuery({
    queryKey: ['paletteSearch', budgetId, searchTerm],
    queryFn: () =>
      apiClient
        .get<BudgetTransactionsResponse>(`/${budgetId}/transactions`, {
          params: { search: searchTerm, limit: 10 },
        })
        .then((r) => r.data),
    enabled: searchOn,
    staleTime: 30_000,
  })

  const payeeMatches = useMemo(() => {
    if (!searchOn) return []
    const q = searchTerm.toLowerCase()
    return payees.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 6)
  }, [payees, searchOn, searchTerm])

  const payeeNameById = useMemo(() => new Map(payees.map((p) => [p.id, p.name])), [payees])

  if (isMobile || !open) return null

  const ctx: CommandCtx = {
    navigate: (to) => navigate(to),
    openQuickAdd,
    openAutoAssign: () => setAutoAssignOpen(true),
    openCoverOverspent: () => setCoverOverspentOpen(true),
    openTbaDrawer: () => setTbaDrawerOpen(true),
    goMonth: (delta) =>
      setSelectedMonth(delta === 0 ? currentMonthStart() : addMonths(selectedMonth, delta)),
  }

  function run(action: () => void) {
    closePalette()
    action()
  }

  const sections: Array<'Actions' | 'Navigate' | 'Tools'> = ['Actions', 'Navigate', 'Tools']

  return (
    <div
      className="palette-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) closePalette()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') closePalette()
      }}
    >
      <Command className="palette" label="Command palette">
        <div className="palette__input-row">
          <Search size={15} className="palette__input-icon" />
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="Search commands, payees, transactions…"
            autoFocus
          />
        </div>
        <Command.List>
          <Command.Empty>No results.</Command.Empty>

          {sections.map((section) => (
            <Command.Group key={section} heading={section}>
              {STATIC_COMMANDS.filter((c) => c.section === section).map((c) => (
                <Command.Item
                  key={c.id}
                  value={c.id}
                  keywords={[c.label, ...(c.keywords?.split(' ') ?? [])]}
                  onSelect={() => run(() => c.run(ctx))}
                >
                  <c.icon size={14} className="palette__item-icon" />
                  {c.label}
                </Command.Item>
              ))}
              {section === 'Navigate' &&
                accounts.map((a) => (
                  <Command.Item
                    key={a.id}
                    value={`account-${a.id}`}
                    keywords={['account', a.name]}
                    onSelect={() => run(() => navigate(`/accounts/${a.id}`))}
                  >
                    <Landmark size={14} className="palette__item-icon" />
                    {a.name}
                  </Command.Item>
                ))}
              {section === 'Navigate' &&
                views.map((v) => (
                  <Command.Item
                    key={v.id}
                    value={`view-${v.id}`}
                    keywords={['view', v.name]}
                    onSelect={() =>
                      run(() => {
                        setActiveBudgetView(v.id)
                        navigate('/budget')
                      })
                    }
                  >
                    <Bookmark size={14} className="palette__item-icon" />
                    View: {v.name}
                  </Command.Item>
                ))}
            </Command.Group>
          ))}

          <Command.Group heading="Theme">
            {THEMES.map((t) => (
              <Command.Item
                key={t.value}
                value={`theme-${t.value}`}
                keywords={['theme', t.label]}
                onSelect={() => run(() => setTheme(t.value))}
              >
                <PaletteIcon size={14} className="palette__item-icon" />
                {t.label}
                {theme === t.value && <span className="palette__item-note">current</span>}
              </Command.Item>
            ))}
          </Command.Group>

          {payeeMatches.length > 0 && (
            <Command.Group heading="Payees">
              {payeeMatches.map((p) => (
                <Command.Item
                  key={p.id}
                  value={`payee-${p.id}`}
                  keywords={[p.name]}
                  onSelect={() => run(() => navigate('/payees'))}
                >
                  <User size={14} className="palette__item-icon" />
                  {p.name}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {searchOn && (txnResults?.transactions.length ?? 0) > 0 && (
            <Command.Group heading="Transactions">
              {txnResults!.transactions.map((t) => (
                <Command.Item
                  key={t.id}
                  value={`txn-${t.id}`}
                  keywords={[
                    t.payee_id ? (payeeNameById.get(t.payee_id) ?? '') : '',
                    t.memo ?? '',
                  ]}
                  onSelect={() => run(() => navigate(`/accounts/${t.account_id}`))}
                >
                  <Receipt size={14} className="palette__item-icon" />
                  <span className="palette__txn-payee">
                    {t.payee_id ? (payeeNameById.get(t.payee_id) ?? 'No payee') : 'No payee'}
                  </span>
                  {t.memo && <span className="palette__txn-memo">{t.memo}</span>}
                  <span className="palette__txn-meta">
                    {formatDate(t.date)} · {formatMoney(Number(t.amount))}
                  </span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </Command>
    </div>
  )
}
