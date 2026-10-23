import { ChevronRight, Search, X } from 'lucide-react'
import { useFormatters } from '../../../hooks/useFormatters'
import { BUDGET_ROW_MODES, type QuickFilter } from '../../../stores/uiStore'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import type { SelectChipGroup } from '../../common/SelectChip/SelectChip'
import type { StatusButton } from '../budgetFilterMenu'
import './BudgetToolsSheet.css'

type RowMode = (typeof BUDGET_ROW_MODES)[number]['value']

interface Props {
  open: boolean
  onClose: () => void
  search: string
  onSearch: (value: string) => void
  /** The five statuses, from `statusButtons` — the bar's own list. */
  statuses: StatusButton[]
  /** Nothing narrows the grid by status or saved filter. */
  showingAll: boolean
  onStatus: (filter: QuickFilter | null) => void
  views: { id: string; name: string }[]
  viewId: string | null
  onView: (viewId: string | null) => void
  /** The saved-filter choices, from `filterMenu` — the bar's own list. */
  filterGroups: SelectChipGroup[]
  filterValue: string
  onFilter: (value: string) => void
  rowMode: RowMode
  onRowMode: (mode: RowMode) => void
  /** New / manage a filter or a view: the bar's menu ids. */
  onManage: (id: 'new' | 'manage' | 'new-view' | 'manage-views') => void
  onMoneyMoved: () => void
  /** What last month's overspending took, or null when it took nothing. */
  lastMonthTotal: number | null
  onLastMonth: () => void
}

/**
 * The budget's tools on a phone, one tap from the Ready to Assign row.
 *
 * On a desktop these are a bar above the grid; on a phone that bar was two
 * rows, and the hero above it wrapped to two more, so the first category
 * started a third of the way down the screen. The controls are the same ones
 * — this renders what BudgetFilterBar already computed (`statusButtons`,
 * `filterMenu`), so a status's count here is the count the desktop bar shows.
 * A sheet rather than a fold: the list never moves under the thumb, and the
 * page keeps its one vertical scroller.
 */
export function BudgetToolsSheet({
  open,
  onClose,
  search,
  onSearch,
  statuses,
  showingAll,
  onStatus,
  views,
  viewId,
  onView,
  filterGroups,
  filterValue,
  onFilter,
  rowMode,
  onRowMode,
  onManage,
  onMoneyMoved,
  lastMonthTotal,
  onLastMonth,
}: Props) {
  const { formatMoney } = useFormatters()

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      height="auto"
      title="Budget tools"
      historyKey="budget-tools"
    >
      <div className="budget-tools">
        <label className="budget-tools__search">
          <Search size={15} aria-hidden="true" />
          <input
            type="search"
            enterKeyHint="search"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Find a category… or tag:essential"
            aria-label="Find a category by name, group, or tag"
          />
          {search && (
            <button
              type="button"
              className="budget-tools__search-clear"
              onClick={() => onSearch('')}
              aria-label="Clear"
            >
              <X size={14} />
            </button>
          )}
        </label>

        <section className="budget-tools__section" aria-label="Show">
          <h3 className="budget-tools__heading">Show</h3>
          <button
            type="button"
            className={`budget-tools__row ${showingAll ? 'active' : ''}`}
            aria-pressed={showingAll}
            onClick={() => onStatus(null)}
          >
            <span className="budget-tools__radio" aria-hidden="true" />
            <span className="budget-tools__row-label">All categories</span>
          </button>
          {statuses.map((s) => (
            <button
              key={s.filter}
              type="button"
              className={`budget-tools__row budget-tools__row--${s.variant} ${s.active ? 'active' : ''}`}
              aria-pressed={s.active}
              disabled={s.disabled}
              onClick={() => onStatus(s.active ? null : s.filter)}
            >
              <span className="budget-tools__radio" aria-hidden="true" />
              <span className="budget-tools__row-label">{s.label}</span>
              <span className="budget-tools__count tabular">{s.countLabel}</span>
            </button>
          ))}
        </section>

        <section className="budget-tools__section" aria-label="Arrange">
          <h3 className="budget-tools__heading">Arrange</h3>
          <div className="budget-tools__selects">
            <label className="budget-tools__select">
              <span>Group by</span>
              <select value={viewId ?? ''} onChange={(e) => onView(e.target.value || null)}>
                <option value="">Default groups</option>
                {views.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="budget-tools__select">
              <span>Saved filter</span>
              <select value={filterValue} onChange={(e) => onFilter(e.target.value)}>
                <option value="">None</option>
                {filterGroups.flatMap((g) =>
                  g.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))
                )}
              </select>
            </label>
          </div>
          <div className="budget-tools__density" role="group" aria-label="Row density">
            {BUDGET_ROW_MODES.map((mode) => (
              <button
                key={mode.value}
                type="button"
                className={rowMode === mode.value ? 'active' : ''}
                aria-pressed={rowMode === mode.value}
                onClick={() => onRowMode(mode.value)}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <div className="budget-tools__manage">
            <button type="button" onClick={() => onManage('new')}>
              New filter
            </button>
            <button type="button" onClick={() => onManage('manage')}>
              Manage filters
            </button>
            <button type="button" onClick={() => onManage('new-view')}>
              New view
            </button>
            <button type="button" onClick={() => onManage('manage-views')}>
              Manage views
            </button>
          </div>
        </section>

        <section className="budget-tools__section" aria-label="This month">
          <h3 className="budget-tools__heading">This month</h3>
          <button type="button" className="budget-tools__link" onClick={onMoneyMoved}>
            <span>Money moved this month</span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
          {lastMonthTotal !== null && (
            <button type="button" className="budget-tools__link" onClick={onLastMonth}>
              <span>Overspent last month</span>
              <span className="budget-tools__link-figure tabular">
                {formatMoney(-lastMonthTotal)}
                <ChevronRight size={16} aria-hidden="true" />
              </span>
            </button>
          )}
        </section>
      </div>
    </BottomSheet>
  )
}
