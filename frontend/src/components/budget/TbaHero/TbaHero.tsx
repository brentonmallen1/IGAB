import { useRef, useState } from 'react'
import { CalendarRange, ChevronDown, History, Wand2, X } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategories } from '../../../api/categories'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { Modal } from '../../common/Modal/Modal'
import { AssignDropdown, AssignDropdownContent } from '../AssignDropdown/AssignDropdown'
import { AssignPreviewModal } from '../AssignPreviewModal/AssignPreviewModal'
import { overspending, overspentLastMonth } from '../budgetTotals'
import { CoverOverspentModal } from './CoverOverspentModal'
import { LastMonthModal } from './LastMonthModal'
import { TbaDrawer } from './TbaDrawer'
import type { AssignStrategy } from '../../../types'
import './TbaHero.css'

interface Props {
  budgetId: string
  month: string
}

/**
 * The centerpiece of the budget page: Ready to Assign, up and center, with the
 * money-movement actions attached — the Assign dropdown (auto strategies,
 * cover overspending, manual assign), the overspent chip that opens the cover
 * flow directly, and a history button that opens the month's move log in a
 * modal so the header never grows.
 */
export function TbaHero({ budgetId, month }: Props) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const isMobile = useIsMobile()
  const { formatMoney } = useFormatters()
  // Archived included: an envelope archived since can still have been red.
  const { data: categories = [] } = useCategories(budgetId, true)

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
  const [showLastMonth, setShowLastMonth] = useState(false)

  const tba = budgetMonth?.to_be_assigned ?? 0
  // One implementation of "how much is overspent" (budgetTotals), shared with
  // the Assign dropdown's Cover row: the two answered it differently until
  // 2026-09-05 and drifted apart exactly as two copies do. The part that rode
  // onto a card is not the header's to say: it is card debt, and it shows
  // where it is acted on — the cards band and each card's detail.
  const { total: overspent } = overspending(budgetMonth)
  const assignedInFuture = Number(budgetMonth?.assigned_in_future ?? 0)
  const tbaClass = tba > 0 ? 'positive' : tba < 0 ? 'negative' : 'zero'

  // Counted server-side beside total_overspent, over the same set. Rebuilt
  // here it read the client's category list, which excludes hidden categories
  // — so the count undercounted next to an amount that included them, and next
  // to a Cover Overspent that would act on them. `overspent_count`, not the
  // `_cash` variant, for the same reason the amount above is the whole red.
  const overspentCount = budgetMonth?.overspent_count ?? 0

  function handlePickStrategy(strategy: AssignStrategy) {
    setAssignOpen(false)
    setPreviewStrategy(strategy)
  }

  function handleCoverFromDropdown() {
    setAssignOpen(false)
    setShowCover(true)
  }

  const history = (
    <TbaDrawer
      budgetId={budgetId}
      month={month}
      open={drawerOpen}
      assignedInFuture={assignedInFuture}
    />
  )

  // A card's envelope is named for its card; everything else by its own name.
  const lastMonth = overspentLastMonth(budgetMonth?.overspent_last_month, (categoryId) => {
    const card = budgetMonth?.cards?.find((c) => c.category_id === categoryId)
    return card?.name ?? categories.find((c) => c.id === categoryId)?.name ?? 'An envelope'
  })

  return (
    <div className="tba-hero">
      <div className="tba-hero__pill">
        <div className="tba-hero__info">
          <span className="tba-hero__label">Ready to Assign</span>
          <span className={`tba-hero__amount ${tbaClass}`}>{formatMoney(tba)}</span>
          {assignedInFuture !== 0 && (
            <span className="tba-hero__future" title="Already deducted from Ready to Assign">
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
              onClick={() => setShowCover(true)}
              title="Cover overspending"
            >
              {formatMoney(-overspent)}
              <span className="tba-hero__chip-word">overspent</span>
            </button>
          )}

          {/* What the 1st took, as a pill like the one beside it. It was a
              sentence listing every envelope, which wrapped into two ragged
              lines under the number; the list is one tap away instead. */}
          {lastMonth && (
            <button
              type="button"
              className="tba-hero__last-month"
              onClick={() => setShowLastMonth(true)}
              aria-haspopup="dialog"
            >
              {formatMoney(-lastMonth.total)}
              <span className="tba-hero__chip-word">overspent last month</span>
            </button>
          )}

          <button
            className="tba-hero__history-btn"
            onClick={() => setDrawerOpen(true)}
            aria-haspopup="dialog"
            aria-label="Money moved this month"
            title="Money moved this month"
          >
            <History size={15} />
          </button>
        </div>
      </div>

      {drawerOpen && !isMobile && (
        <Modal onClose={() => setDrawerOpen(false)} historyKey="tba-history">
          <div
            className="tba-history-modal"
            role="dialog"
            aria-modal
            aria-labelledby="tba-history-title"
          >
            <div className="tba-history-modal__header">
              <span id="tba-history-title" className="tba-history-modal__title">
                <History size={14} />
                Money moved this month
              </span>
              <button
                className="tba-history-modal__close"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>
            <div className="tba-history-modal__body scroll-fill">{history}</div>
          </div>
        </Modal>
      )}
      {isMobile && (
        <BottomSheet
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          height="auto"
          title="Money moved this month"
          historyKey="tba-drawer"
        >
          {history}
        </BottomSheet>
      )}

      {assignOpen && !isMobile && (
        <AssignDropdown
          anchorRef={assignRef}
          budgetId={budgetId}
          month={month}
          tba={tba}
          overspentCount={overspentCount}
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
            tba={tba}
            overspentCount={overspentCount}
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
      {showLastMonth && lastMonth && (
        <LastMonthModal
          month={month}
          lastMonth={lastMonth}
          onClose={() => setShowLastMonth(false)}
        />
      )}
      {showCover && (
        <CoverOverspentModal
          budgetId={budgetId}
          month={month}
          onClose={() => setShowCover(false)}
        />
      )}
    </div>
  )
}
