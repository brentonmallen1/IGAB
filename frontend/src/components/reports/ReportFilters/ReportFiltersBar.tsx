import { useMemo } from 'react'
import { RotateCcw } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useBudgetViews } from '../../../api/budgetViews'
import { categoryOptions } from './categoryOptions'
import { usePayees } from '../../../api/payees'
import { useAccounts } from '../../../api/accounts'
import {
  resolveGroupBy,
  useReportStore,
  TAB_FILTER_SUPPORT,
  type GroupBy,
} from '../../../stores/reportStore'
import { DateRangePicker } from './DateRangePicker'
import { MultiSelectCombobox } from './MultiSelectCombobox'
import type { MultiSelectOption } from './MultiSelectCombobox'
import './ReportFiltersBar.css'
import { Surface } from '../../common/Surface'
import { openAccounts } from '../../../utils/accountLists'
import { useTags } from '../../../api/tags'
import { useBudgetFilters } from '../../../api/budgetFilters'
import { countActiveFilters, hasAnyFilterSupport } from './activeFilters'

interface Props {
  budgetId: string
}

const GROUP_BY_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: 'group', label: 'Group' },
  { value: 'category', label: 'Category' },
  { value: 'payee', label: 'Payee' },
]

/** The bar as the desktop draws it: one chrome band above the report. */
export function ReportFiltersBar({ budgetId }: Props) {
  const { activeTab } = useReportStore()
  if (!hasAnyFilterSupport(activeTab)) return null
  return (
    <Surface variant="chrome" className="rfb">
      <ReportFiltersContent budgetId={budgetId} />
    </Surface>
  )
}

/**
 * The controls themselves, container-free: the desktop bar wraps them in a
 * chrome band, the phone puts them in a sheet behind a Filters chip. One
 * implementation of the pickers either way.
 */
export function ReportFiltersContent({ budgetId }: Props) {
  const { filters, setFilters, resetFilters, activeTab } = useReportStore()
  const support = TAB_FILTER_SUPPORT[activeTab]
  const categories = useCategories(budgetId)
  const groups = useCategoryGroups(budgetId)
  const payees = usePayees(budgetId)
  const accounts = useAccounts(budgetId)
  const views = useBudgetViews(budgetId)
  const tags = useTags(budgetId)
  const savedFilters = useBudgetFilters(budgetId)

  const groupMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of groups.data ?? []) m.set(g.id, g.name)
    return m
  }, [groups.data])

  // Only on tabs that actually roll up by a view. The preference is stored
  // once and shared, so a view picked on Pareto reached tabs with no view
  // selector and no view_id in their request — narrowing the category picker
  // to a view the report was ignoring, with no control on that tab to undo it.
  const activeView = useMemo(
    () => (support.views ? (views.data?.find((v) => v.id === filters.viewId) ?? null) : null),
    [support.views, views.data, filters.viewId]
  )

  const categoryOpts = useMemo(
    () => categoryOptions(categories.data ?? [], groupMap, activeView),
    [categories.data, groupMap, activeView]
  )

  const tagOptions = useMemo<MultiSelectOption[]>(
    () => (tags.data ?? []).map((t) => ({ id: t.id, label: t.name })),
    [tags.data]
  )

  const payeeOptions = useMemo<MultiSelectOption[]>(() => {
    return (payees.data ?? [])
      .filter((p) => !p.transfer_account_id)
      .map((p) => ({ id: p.id, label: p.name }))
  }, [payees.data])

  const accountOptions = useMemo<MultiSelectOption[]>(() => {
    return openAccounts(accounts.data ?? []).map((a) => ({ id: a.id, label: a.name }))
  }, [accounts.data])

  // viewId counts: it is sent on every request and changes what the report
  // shows. Leaving it out meant a view carried over from another budget was
  // narrowing reports with no selector rendered (that budget has no views)
  // and no Reset offered — unreachable dead state.
  const hasFilters = countActiveFilters(filters) > 0

  if (!hasAnyFilterSupport(activeTab)) return null

  return (
    <>
      <div className="rfb__row">
        {support.dates && (
          <DateRangePicker
            startDate={filters.startDate}
            endDate={filters.endDate}
            onChange={(startDate, endDate) => setFilters({ startDate, endDate })}
          />
        )}
        {support.views && (views.data?.length ?? 0) > 0 && (
          <label className="rfb__view">
            <span className="rfb__view-label">View</span>
            <select
              className={`rfb__view-select ${filters.viewId ? 'rfb__view-select--active' : ''}`}
              value={filters.viewId ?? ''}
              onChange={(e) => setFilters({ viewId: e.target.value || null })}
              title="Roll up by a saved view's groups instead of your own"
            >
              <option value="">Default groups</option>
              {views.data!.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {support.groupBy && (
          <div className="rfb__groupby">
            <span className="rfb__groupby-label">Group by</span>
            {GROUP_BY_OPTIONS.filter(
              (opt) => !support.groupByModes || support.groupByModes.includes(opt.value)
            ).map((opt) => (
              <button
                key={opt.value}
                className={`rfb__groupby-btn ${resolveGroupBy(activeTab, filters.groupBy) === opt.value ? 'rfb__groupby-btn--active' : ''}`}
                onClick={() => setFilters({ groupBy: opt.value })}
                type="button"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
      {(support.categories || support.payees || support.accounts) && (
        <div className="rfb__selects">
          {/* Three ways of saying which categories this report is about, kept
              adjacent because they are one question. They UNION on the server
              (services/report_scope.py): each adds to the scope. A tag needs no
              saved row, so it stays dynamic; a saved filter is the one you
              chose to name, and carries its own tag axis. */}
          {support.categories && (
            <MultiSelectCombobox
              label="Categories"
              selectedIds={filters.categoryIds}
              options={categoryOpts}
              onChange={(ids) => setFilters({ categoryIds: ids })}
              placeholder="All categories"
            />
          )}
          {support.categories && tagOptions.length > 0 && (
            <MultiSelectCombobox
              label="Tags"
              selectedIds={filters.tagIds}
              options={tagOptions}
              onChange={(ids) => setFilters({ tagIds: ids })}
              placeholder="Any tag"
            />
          )}
          {support.categories && (savedFilters.data?.length ?? 0) > 0 && (
            <label className="rfb__view">
              <span className="rfb__view-label">Saved filter</span>
              <select
                className={`rfb__view-select ${filters.filterId ? 'rfb__view-select--active' : ''}`}
                value={filters.filterId ?? ''}
                onChange={(e) => setFilters({ filterId: e.target.value || null })}
                title="Scope by a filter you saved on the budget page"
              >
                <option value="">Any saved filter</option>
                {savedFilters.data!.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          {support.payees && (
            <MultiSelectCombobox
              label="Payees"
              selectedIds={filters.payeeIds}
              options={payeeOptions}
              onChange={(ids) => setFilters({ payeeIds: ids })}
              placeholder="All payees"
            />
          )}
          {support.accounts && (
            <MultiSelectCombobox
              label="Accounts"
              selectedIds={filters.accountIds}
              options={accountOptions}
              onChange={(ids) => setFilters({ accountIds: ids })}
              placeholder="All accounts"
            />
          )}
          {hasFilters && (
            <button
              className="rfb__reset"
              onClick={resetFilters}
              type="button"
              title="Reset filters"
            >
              <RotateCcw size={13} />
              Reset
            </button>
          )}
        </div>
      )}
    </>
  )
}
