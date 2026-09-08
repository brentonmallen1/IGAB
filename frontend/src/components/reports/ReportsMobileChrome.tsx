import { useState } from 'react'
import { ChevronDown, SlidersHorizontal, Star } from 'lucide-react'
import { BottomSheet } from '../common/BottomSheet/BottomSheet'
import { SelectionSheet, type SelectionSheetOption } from '../common/SelectionSheet/SelectionSheet'
import { REPORT_TABS, TAB_GROUPS, useReportStore, type ReportTab } from '../../stores/reportStore'
import { FAVORITES_LABEL } from '../../pages/ReportsPage/reportNav'
import { countActiveFilters, hasAnyFilterSupport } from './ReportFilters/activeFilters'
import { ReportFiltersContent } from './ReportFilters/ReportFiltersBar'
import './ReportsMobileChrome.css'

interface Props {
  budgetId: string
  starred: readonly ReportTab[]
  onToggleStar: () => void
  starPending: boolean
}

/**
 * The reports chrome on a phone: one row.
 *
 * The desktop nav is a group dropdown plus a scrolling tab strip, and the
 * filter bar under it wraps into four or five rows on a 390pt screen — up to
 * seven bands before the chart. Here the report is picked from a searchable
 * sheet grouped by section (Favorites on top), the star stays, and every
 * filter lives behind one chip that says how many are in force.
 */
export function ReportsMobileChrome({ budgetId, starred, onToggleStar, starPending }: Props) {
  const { activeTab, setActiveTab, filters } = useReportStore()
  const setNavFavorites = useReportStore((s) => s.setNavFavorites)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)

  const active = REPORT_TABS.find((t) => t.id === activeTab)
  const isStarred = starred.includes(activeTab)
  const filterCount = countActiveFilters(filters)
  const hasFilters = hasAnyFilterSupport(activeTab)

  const groupLabel = (id: string) => TAB_GROUPS.find((g) => g.id === id)?.label ?? ''
  const options: SelectionSheetOption[] = REPORT_TABS.map((t) => ({
    id: t.id,
    label: t.label,
    group: groupLabel(t.group),
  }))
  const favorites: SelectionSheetOption[] = starred
    .map((id) => REPORT_TABS.find((t) => t.id === id))
    .filter((t): t is (typeof REPORT_TABS)[number] => t !== undefined)
    .map((t) => ({ id: t.id, label: t.label }))

  return (
    <div className="reports-chrome">
      <button
        type="button"
        className="reports-chrome__picker"
        onClick={() => setPickerOpen(true)}
        aria-haspopup="dialog"
      >
        <span className="reports-chrome__picker-label">{active?.label ?? 'Reports'}</span>
        <ChevronDown size={16} aria-hidden />
      </button>

      <button
        type="button"
        className={`reports-chrome__star ${isStarred ? 'reports-chrome__star--on' : ''}`}
        onClick={onToggleStar}
        disabled={starPending}
        aria-pressed={isStarred}
        aria-label={isStarred ? 'Remove from favorites' : 'Add to favorites'}
      >
        <Star size={18} fill={isStarred ? 'currentColor' : 'none'} />
      </button>

      {hasFilters && (
        <button
          type="button"
          className={`reports-chrome__filters ${filterCount > 0 ? 'reports-chrome__filters--active' : ''}`}
          onClick={() => setFiltersOpen(true)}
          aria-haspopup="dialog"
        >
          <SlidersHorizontal size={16} aria-hidden />
          <span>Filters</span>
          {filterCount > 0 && <span className="reports-chrome__count">{filterCount}</span>}
        </button>
      )}

      <SelectionSheet
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        title="Reports"
        options={options}
        value={activeTab}
        onChange={(id) => {
          if (!id) return
          setActiveTab(id as ReportTab)
          setNavFavorites(favorites.some((f) => f.id === id))
        }}
        topSection={
          favorites.length > 0 ? { label: FAVORITES_LABEL, options: favorites } : undefined
        }
        placeholder="Find a report…"
      />

      {filtersOpen && (
        <BottomSheet
          open
          onClose={() => setFiltersOpen(false)}
          title="Filters"
          height="full"
          historyKey="report-filters"
          footer={
            <button
              type="button"
              className="reports-chrome__done"
              onClick={() => setFiltersOpen(false)}
            >
              Done
            </button>
          }
        >
          <div className="reports-chrome__filters-body">
            <ReportFiltersContent budgetId={budgetId} />
          </div>
        </BottomSheet>
      )}
    </div>
  )
}
