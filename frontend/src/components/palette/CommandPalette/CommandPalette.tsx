import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Landmark, Palette as PaletteIcon, Receipt, Search, User, Bookmark, X } from 'lucide-react'
import { apiClient } from '../../../api/client'
import { useAccounts } from '../../../api/accounts'
import { usePayees } from '../../../api/payees'
import { useCategories } from '../../../api/categories'
import { transactionFilterParams } from '../../../api/transactions'
import { useBudgetFilters } from '../../../api/budgetFilters'
import { matchSuggestions, parseTransactionSearch } from '../../../utils/searchParser'
import { useAppStore } from '../../../stores/appStore'
import { useUIStore } from '../../../stores/uiStore'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useHistoryDismissable } from '../../../hooks/useHistoryDismissable'
import { useShortcut } from '../../../hooks/useShortcut'
import { useFormatters } from '../../../hooks/useFormatters'
import { addMonths, currentMonthStart } from '../../../utils/dates'
import { THEMES } from '../../../stores/appStore'
import { STATIC_COMMANDS, type CommandCtx } from '../commands'
import type { BudgetTransactionsResponse } from '../../../types'
import './CommandPalette.css'

/**
 * ⌘K command palette: navigation, budget actions, theme switching, and live
 * payee/transaction search. On mobile it opens from the header's magnifier as
 * a full-width top sheet — it is the only global search affordance on phones
 * (the button used to flip state that nothing consumed: a dead control).
 */
export function CommandPalette() {
  const { formatMoney, formatDate } = useFormatters()
  const isMobile = useIsMobile()
  const navigate = useNavigate()

  const open = useUIStore((s) => s.isPaletteOpen)
  const closePalette = useUIStore((s) => s.closePalette)
  const togglePalette = useUIStore((s) => s.togglePalette)
  const openQuickAdd = useUIStore((s) => s.openQuickAdd)
  const setAssignPreviewStrategy = useUIStore((s) => s.setAssignPreviewStrategy)
  const setCoverOverspentOpen = useUIStore((s) => s.setCoverOverspentOpen)
  const setTbaDrawerOpen = useUIStore((s) => s.setTbaDrawerOpen)
  const setActiveFilter = useUIStore((s) => s.setActiveFilter)

  const budgetId = useAppStore((s) => s.currentBudgetId)
  const selectedMonth = useAppStore((s) => s.selectedMonth)
  const setSelectedMonth = useAppStore((s) => s.setSelectedMonth)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const togglePrivacyMode = useAppStore((s) => s.togglePrivacyMode)

  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')

  useShortcut('mod+k', () => togglePalette(), { allowInInputs: true, enabled: !isMobile })

  // Android back / iOS edge-swipe dismisses the palette instead of leaving
  // the page — same pattern as every mobile sheet.
  useHistoryDismissable(open && isMobile, closePalette, 'palette')

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
  const { data: categories = [] } = useCategories(open ? budgetId : null)
  const { data: filters = [] } = useBudgetFilters(open ? budgetId : null)

  const searchTerm = debounced.trim()
  const searchOn = open && !!budgetId && searchTerm.length >= 2

  // The palette speaks the register's search language rather than a poorer
  // dialect of its own: `date: 3/1-3/15`, `amount:>100`, `category:"Rent"`
  // and the rest all work here, across every account at once.
  const categoryMap = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories])
  const payeeMap = useMemo(() => new Map(payees.map((p) => [p.id, p.name])), [payees])
  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.id, a.name])), [accounts])
  const txnFilters = useMemo(
    () => parseTransactionSearch(searchTerm, categoryMap, payeeMap, accountMap),
    [searchTerm, categoryMap, payeeMap, accountMap]
  )

  const { data: txnResults } = useQuery({
    queryKey: ['paletteSearch', budgetId, txnFilters],
    queryFn: () =>
      apiClient
        .get<BudgetTransactionsResponse>(`/${budgetId}/transactions`, {
          // The same serializer the registers use — a second copy here is how
          // the palette would drift into supporting fewer filters than the
          // search box that taught the user the syntax.
          params: { ...transactionFilterParams(txnFilters), limit: 10 },
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

  const payeeNameById = payeeMap

  if (!open) return null

  const ctx: CommandCtx = {
    navigate: (to) => navigate(to),
    openQuickAdd,
    openAutoAssign: () => setAssignPreviewStrategy('underfunded'),
    openCoverOverspent: () => setCoverOverspentOpen(true),
    openTbaDrawer: () => setTbaDrawerOpen(true),
    goMonth: (delta) =>
      setSelectedMonth(delta === 0 ? currentMonthStart() : addMonths(selectedMonth, delta)),
    togglePrivacy: togglePrivacyMode,
  }

  function run(action: () => void) {
    closePalette()
    action()
  }

  const sections: Array<'Actions' | 'Navigate' | 'Tools'> = ['Actions', 'Navigate', 'Tools']

  /** Substring match over an item's own words. Deliberately plainer than the
   *  fuzzy scorer it replaces: these lists are short and known, and a command
   *  the user typed the name of must never be the thing that gets hidden. */
  const q = query.trim().toLowerCase()
  const hit = (...words: (string | undefined)[]) =>
    !q || words.some((w) => w?.toLowerCase().includes(q))

  const visibleCommands = STATIC_COMMANDS.filter((c) => hit(c.id, c.label, c.keywords))
  const visibleAccounts = accounts.filter((a) => hit(a.name, 'account'))
  const visibleFilters = filters.filter((f) => hit(f.name, 'view', 'filter'))
  const visibleThemes = THEMES.filter((t) => hit(t.label, 'theme'))

  // Only once the query looks like the start of a filter token. Offering the
  // whole vocabulary against an ordinary word ("grocer") would bury the rows
  // the user is actually looking for under syntax they didn't ask about.
  const suggestions = /[a-z]+:|^(NOT|OR)\b/i.test(query.trim())
    ? matchSuggestions(query).slice(0, 5)
    : []

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
      {/* shouldFilter={false} is load-bearing. cmdk's default filter scores
          each item's `value` + `keywords` and hides anything scoring zero —
          which it applied ON TOP of results the server had already matched.
          A transaction's amount is rendered but is in neither field, so
          "12.34" scored zero on every row and the palette showed "No
          results" over a correct answer. ("12" appeared to work only because
          those digits turn up inside a hex uuid.) Server-matched groups are
          rendered as returned; the fixed lists below filter themselves. */}
      <Command className="palette" label="Command palette" shouldFilter={false}>
        <div className="palette__input-row">
          <Search size={15} className="palette__input-icon" />
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="Search commands, payees, transactions…"
            autoFocus
            enterKeyHint="go"
          />
          {/* Mobile-only (CSS): the backdrop is a sliver on a full-width
              sheet, and a standalone PWA has no browser back button. */}
          <button
            type="button"
            className="palette__close"
            onClick={closePalette}
            aria-label="Close search"
          >
            <X size={18} />
          </button>
        </div>
        <Command.List>
          <Command.Empty>No results.</Command.Empty>

          {sections.map((section) => (
            <Command.Group key={section} heading={section}>
              {visibleCommands.filter((c) => c.section === section).map((c) => (
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
                visibleAccounts.map((a) => (
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
                visibleFilters.map((v) => (
                  <Command.Item
                    key={v.id}
                    value={`view-${v.id}`}
                    keywords={['view', v.name]}
                    onSelect={() =>
                      run(() => {
                        setActiveFilter(v.id)
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
            {visibleThemes.map((t) => (
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
                  onSelect={() => run(() => navigate(`/payees?q=${encodeURIComponent(p.name)}`))}
                >
                  <User size={14} className="palette__item-icon" />
                  {p.name}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {suggestions.length > 0 && (
            <Command.Group heading="Search syntax">
              {suggestions.map((s) => (
                <Command.Item
                  key={s.syntax}
                  value={`suggest-${s.syntax}`}
                  // Completes the query in place rather than running
                  // anything — the palette stays open and the user keeps
                  // typing, same as the register's search box.
                  onSelect={() => {
                    const trimmed = query.trimEnd()
                    setQuery(trimmed.slice(0, trimmed.length - s.matchedLen) + s.syntax)
                  }}
                >
                  <Search size={14} className="palette__item-icon" />
                  <span className="palette__txn-payee">{s.syntax.trim()}</span>
                  <span className="palette__txn-memo">{s.description}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {searchOn && (
            <Command.Group heading="Transactions">
              {/* The palette shows ten rows; the register shows all of them,
                  with the same query already applied. Pinned above the
                  preview so the way to the full answer is always in the same
                  place, whether ten rows came back or none. */}
              <Command.Item
                value="search-all-transactions"
                onSelect={() =>
                  run(() => navigate(`/transactions?q=${encodeURIComponent(searchTerm)}`))
                }
              >
                <Search size={14} className="palette__item-icon" />
                Search all transactions for “{searchTerm}”
                {(txnResults?.total_count ?? 0) > 0 && (
                  <span className="palette__item-note">
                    {txnResults!.total_count.toLocaleString()} match
                    {txnResults!.total_count === 1 ? '' : 'es'}
                  </span>
                )}
              </Command.Item>
              {(txnResults?.transactions ?? []).map((t) => (
                <Command.Item
                  key={t.id}
                  value={`txn-${t.id}`}
                  keywords={[
                    t.payee_id ? (payeeNameById.get(t.payee_id) ?? '') : '',
                    t.memo ?? '',
                  ]}
                  onSelect={() => run(() => navigate(`/accounts/${t.account_id}?highlight=${t.id}`))}
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
