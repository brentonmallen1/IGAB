import { useMemo, useRef } from 'react'
import { CalendarRange, ChevronDown, Wand2 } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { AssignDropdown, AssignDropdownContent } from '../AssignDropdown/AssignDropdown'
import { AssignPreviewModal } from '../AssignPreviewModal/AssignPreviewModal'
import { CoverOverspentModal } from './CoverOverspentModal'
import { TbaDrawer } from './TbaDrawer'
import type { AssignStrategy } from '../../../types'
import './TbaHero.css'

interface Props {
  budgetId: string
  month: string
}

/**
 * The centerpiece of the budget page: To Be Assigned, up and center, with the
 * money-movement actions attached — the Assign dropdown (auto strategies +
 * manual assign), cover overspending, and a drawer holding the overspending
 * summary and the month's move log.
 */
export function TbaHero({ budgetId, month }: Props) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const isMobile = useIsMobile()
  const { formatMoney } = useFormatters()

  const drawerOpen = useUIStore((s) => s.tbaDrawerOpen)
  const setDrawerOpen = useUIStore((s) => s.setTbaDrawerOpen)
  const assignOpen = useUIStore((s) => s.assignDropdownOpen)
  const setAssignOpen = useUIStore((s) => s.setAssignDropdownOpen)
  const previewStrategy = useUIStore((s) => s.assignPreviewStrategy)
  const setPreviewStrategy = useUIStore((s) => s.setAssignPreviewStrategy)
  const showCover = useUIStore((s) => s.isCoverOverspentOpen)
  const setShowCover = useUIStore((s) => s.setCoverOverspentOpen)
  const setMultiMonthOpen = useUIStore((s) => s.setMultiMonthOpen)
  const assignRef = useRef<HTMLDivElement>(null)

  const tba = budgetMonth?.to_be_assigned ?? 0
  const overspent = Number(budgetMonth?.total_overspent ?? 0)
  const assignedInFuture = Number(budgetMonth?.assigned_in_future ?? 0)
  const tbaClass = tba > 0 ? 'positive' : tba < 0 ? 'negative' : 'zero'

  const overspentCount = useMemo(() => {
    const systemGroupIds = new Set(groups.filter((g) => g.is_system).map((g) => g.id))
    const nonSystemIds = new Set(
      categories.filter((c) => !systemGroupIds.has(c.category_group_id)).map((c) => c.id)
    )
    return (budgetMonth?.category_balances ?? []).filter(
      (b) => b.available < 0 && nonSystemIds.has(b.category_id)
    ).length
  }, [budgetMonth, categories, groups])

  function handlePickStrategy(strategy: AssignStrategy) {
    setAssignOpen(false)
    setPreviewStrategy(strategy)
  }

  function handleCoverFromDropdown() {
    setAssignOpen(false)
    setShowCover(true)
  }

  function openCoverFromDrawer() {
    setDrawerOpen(false)
    setShowCover(true)
  }

  const drawer = (
    <TbaDrawer
      budgetId={budgetId}
      month={month}
      open={drawerOpen}
      totalOverspent={overspent}
      overspentCount={overspentCount}
      assignedInFuture={assignedInFuture}
      onCoverOverspent={openCoverFromDrawer}
    />
  )

  return (
    <div className="tba-hero">
      <div className="tba-hero__pill">
        <div className="tba-hero__info">
          <span className="tba-hero__label">To Be Assigned</span>
          <span className={`tba-hero__amount ${tbaClass}`}>{formatMoney(tba)}</span>
          {assignedInFuture !== 0 && (
            <span className="tba-hero__future" title="Already deducted from To Be Assigned">
              {formatMoney(assignedInFuture)} assigned in future months
            </span>
          )}
        </div>

        <div className="tba-hero__actions">
          <div className="tba-hero__assign" ref={assignRef}>
            <button
              className="tba-hero__assign-main"
              onClick={() => setAssignOpen(!assignOpen)}
              aria-expanded={assignOpen}
              aria-haspopup="menu"
              title="Assign money"
            >
              <Wand2 size={13} />
              Assign
              <ChevronDown size={13} />
            </button>
          </div>

          {!isMobile && (
            <button
              className="tba-hero__months-btn"
              onClick={() => setMultiMonthOpen(true)}
              title="Side-by-side multi-month view"
            >
              <CalendarRange size={13} />
              Months
            </button>
          )}

          {overspent > 0 && (
            <button
              className="tba-hero__overspent-chip"
              onClick={() => setDrawerOpen(!drawerOpen)}
              title="Show overspending details"
            >
              {formatMoney(-overspent)}
              <span className="tba-hero__chip-word"> overspent</span>
            </button>
          )}

          <button
            className={`tba-hero__caret ${drawerOpen ? 'tba-hero__caret--open' : ''}`}
            onClick={() => setDrawerOpen(!drawerOpen)}
            aria-expanded={drawerOpen}
            aria-label="Toggle month details"
            title="Overspending and move history"
          >
            <ChevronDown size={16} />
          </button>
        </div>
      </div>

      {drawerOpen && !isMobile && <div className="tba-hero__drawer">{drawer}</div>}
      {isMobile && (
        <BottomSheet
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          height="auto"
          title="This month"
          historyKey="tba-drawer"
        >
          {drawer}
        </BottomSheet>
      )}

      {assignOpen && !isMobile && (
        <AssignDropdown
          anchorRef={assignRef}
          budgetId={budgetId}
          month={month}
          tba={Number(tba)}
          onPickStrategy={handlePickStrategy}
          onCoverOverspent={handleCoverFromDropdown}
          onClose={() => setAssignOpen(false)}
        />
      )}
      {isMobile && (
        <BottomSheet
          open={assignOpen}
          onClose={() => setAssignOpen(false)}
          height="auto"
          title="Assign"
          historyKey="assign-menu"
        >
          <AssignDropdownContent
            budgetId={budgetId}
            month={month}
            tba={Number(tba)}
            onPickStrategy={handlePickStrategy}
            onCoverOverspent={handleCoverFromDropdown}
            onClose={() => setAssignOpen(false)}
          />
        </BottomSheet>
      )}

      {previewStrategy !== null && (
        <AssignPreviewModal
          budgetId={budgetId}
          month={month}
          strategy={previewStrategy}
          onClose={() => setPreviewStrategy(null)}
        />
      )}
      {showCover && (
        <CoverOverspentModal budgetId={budgetId} month={month} onClose={() => setShowCover(false)} />
      )}
    </div>
  )
}
