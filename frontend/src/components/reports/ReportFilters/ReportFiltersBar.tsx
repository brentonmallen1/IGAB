import { useMemo } from 'react'
import { RotateCcw } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useBudgetViews } from '../../../api/budgetViews'
import { categoryOptions } from './categoryOptions'
import { usePayees } from '../../../api/payees'
import { useAccounts } from '../../../api/accounts'
import { useReportStore, TAB_FILTER_SUPPORT, type GroupBy } from '../../../stores/reportStore'
import { DateRangePicker } from './DateRangePicker'
import { MultiSelectCombobox } from './MultiSelectCombobox'
import type { MultiSelectOption } from './MultiSelectCombobox'
import './ReportFiltersBar.css'

interface Props {
  budgetId: string
}

const GROUP_BY_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: 'group', label: 'Group' },
  { value: 'category', label: 'Category' },
  { value: 'payee', label: 'Payee' },
]

export function ReportFiltersBar({ budgetId }: Props) {
  const { filters, setFilters, resetFilters, activeTab } = useReportStore()
  const support = TAB_FILTER_SUPPORT[activeTab]
  const categories = useCategories(budgetId)
  const groups = useCategoryGroups(budgetId)
  const payees = usePayees(budgetId)
  const accounts = useAccounts(budgetId)
  const views = useBudgetViews(budgetId)

  const groupMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of groups.data ?? []) m.set(g.id, g.name)
    return m
  }, [groups.data])

  const activeView = useMemo(
    () => views.data?.find((v) => v.id === filters.viewId) ?? null,
    [views.data, filters.viewId]
  )

  const categoryOpts = useMemo(
    () => categoryOptions(categories.data ?? [], groupMap, activeView),
    [categories.data, groupMap, activeView]
  )

  const payeeOptions = useMemo<MultiSelectOption[]>(() => {
    return (payees.data ?? [])
      .filter((p) => !p.transfer_account_id)
      .map((p) => ({ id: p.id, label: p.name }))
  }, [payees.data])

  const accountOptions = useMemo<MultiSelectOption[]>(() => {
    return (accounts.data ?? [])
      .filter((a) => !a.is_closed)
      .map((a) => ({ id: a.id, label: a.name }))
  }, [accounts.data])

  const hasFilters =
    filters.categoryIds.length > 0 ||
    filters.payeeIds.length > 0 ||
    filters.accountIds.length > 0

  // Check if any filters are supported for this tab
  const hasAnySupport =
    support.dates ||
    support.categories ||
    support.payees ||
    support.accounts ||
    support.groupBy ||
    support.views

  // If no filters apply, don't render the bar
  if (!hasAnySupport) {
    return null
  }

  return (
    <div className="rfb">
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
            {GROUP_BY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`rfb__groupby-btn ${filters.groupBy === opt.value ? 'rfb__groupby-btn--active' : ''}`}
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
          {support.categories && (
            <MultiSelectCombobox
              label="Categories"
              selectedIds={filters.categoryIds}
              options={categoryOpts}
              onChange={(ids) => setFilters({ categoryIds: ids })}
              placeholder="All categories"
            />
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
            <button className="rfb__reset" onClick={resetFilters} type="button" title="Reset filters">
              <RotateCcw size={13} />
              Reset
            </button>
          )}
        </div>
      )}
    </div>
  )
}
