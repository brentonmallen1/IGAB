import { useMemo } from 'react'
import { RotateCcw } from 'lucide-react'
import { useCategories, useCategoryGroups } from '../../../api/categories'
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

const NOT_USED = 'Not used by this report'

export function ReportFiltersBar({ budgetId }: Props) {
  const { filters, setFilters, resetFilters, activeTab } = useReportStore()
  const support = TAB_FILTER_SUPPORT[activeTab]
  const categories = useCategories(budgetId)
  const groups = useCategoryGroups(budgetId)
  const payees = usePayees(budgetId)
  const accounts = useAccounts(budgetId)

  const groupMap = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of groups.data ?? []) m.set(g.id, g.name)
    return m
  }, [groups.data])

  const categoryOptions = useMemo<MultiSelectOption[]>(() => {
    return (categories.data ?? [])
      .filter((c) => !c.is_hidden)
      .map((c) => ({ id: c.id, label: c.name, group: groupMap.get(c.category_group_id) ?? '' }))
  }, [categories.data, groupMap])

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

  return (
    <div className="rfb">
      <div className="rfb__row">
        <div
          className={support.dates ? undefined : 'rfb__inert'}
          title={support.dates ? undefined : NOT_USED}
        >
          <DateRangePicker
            startDate={filters.startDate}
            endDate={filters.endDate}
            onChange={(startDate, endDate) => setFilters({ startDate, endDate })}
          />
        </div>
        <div
          className={`rfb__groupby ${support.groupBy ? '' : 'rfb__inert'}`}
          title={support.groupBy ? undefined : NOT_USED}
        >
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
      </div>
      <div className="rfb__selects">
        <MultiSelectCombobox
          label="Categories"
          selectedIds={filters.categoryIds}
          options={categoryOptions}
          onChange={(ids) => setFilters({ categoryIds: ids })}
          placeholder="All categories"
          disabled={!support.categories}
          title={NOT_USED}
        />
        <MultiSelectCombobox
          label="Payees"
          selectedIds={filters.payeeIds}
          options={payeeOptions}
          onChange={(ids) => setFilters({ payeeIds: ids })}
          placeholder="All payees"
          disabled={!support.payees}
          title={NOT_USED}
        />
        <MultiSelectCombobox
          label="Accounts"
          selectedIds={filters.accountIds}
          options={accountOptions}
          onChange={(ids) => setFilters({ accountIds: ids })}
          placeholder="All accounts"
          disabled={!support.accounts}
          title={NOT_USED}
        />
        {hasFilters && (
          <button className="rfb__reset" onClick={resetFilters} type="button" title="Reset filters">
            <RotateCcw size={13} />
            Reset
          </button>
        )}
      </div>
    </div>
  )
}
