import { useRef } from 'react'
import { CalendarRange, ChevronDown, History, Wand2, X } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useUIStore } from '../../../stores/uiStore'
import { useFormatters } from '../../../hooks/useFormatters'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { Modal } from '../../common/Modal/Modal'
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
 * money-movement actions attached — the Assign dropdown (auto strategies,
 * cover overspending, manual assign), the overspent chip that opens the cover
 * flow directly, and a history button that opens the month's move log in a
 * modal so the header never grows.
 */
export function TbaHero({ budgetId, month }: Props) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
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
  // The cash part leads, because it is the only part an action can change:
  // it is written off from Ready to Assign at the month boundary. Credit
  // overspending rode onto a card, is already counted in that card's
  // Uncovered, and rolls onto it when the month turns — there is nothing to
  // do about it, so it must not be dressed as work. See domain/cards.py.
  const overspent = Number(budgetMonth?.total_overspent_cash ?? 0)
  const overspentOnCards = Number(budgetMonth?.total_overspent_credit ?? 0)
  const assignedInFuture = Number(budgetMonth?.assigned_in_future ?? 0)
  const tbaClass = tba > 0 ? 'positive' : tba < 0 ? 'negative' : 'zero'

  // Counted server-side beside total_overspent, over the same set. Rebuilt
  // here it read the client's category list, which excludes hidden categories
  // — so the count undercounted next to an amount that included them, and next
  // to a Cover Overspent that would act on them.
  const overspentCount = budgetMonth?.overspent_count_cash ?? 0

  function handlePickStrategy(strategy: AssignStrategy) {
    setAssignOpen(false)
    setPreviewStrategy(strategy)
  }

  function handleCoverFromDropdown() {
    setAssignOpen(false)
    setShowCover(true)
  }

  const history = (
    <TbaDrawer budgetId={budgetId} month={month} open={drawerOpen} assignedInFuture={assignedInFuture} />
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
              onClick={() => setShowCover(true)}
              title={
                overspentOnCards > 0
                  ? `${formatMoney(-overspent)} overspent in cash — covered from To Be Assigned ` +
                    `when the month turns. A further ${formatMoney(overspentOnCards)} was spent ` +
                    `on cards and rides there as debt instead; it never charges To Be Assigned.`
                  : 'Cover overspending'
              }
            >
              {formatMoney(-overspent)}
              <span className="tba-hero__chip-word">overspent</span>
            </button>
          )}

          {/* Card-funded red, stated and not alarmed about: it costs nothing
              and there is no action attached, so it gets the same calm
              treatment as Uncovered in the cards section. Shown even when the
              cash chip is absent — otherwise a month overspent entirely on a
              card looks like a month with no overspending at all, and the
              grid's red would have nothing explaining it. */}
          {overspentOnCards > 0 && (
            <span
              className="tba-hero__on-cards"
              title={
                `${formatMoney(overspentOnCards)} of this month's overspending was spent on a ` +
                `card. It is already counted in that card's Uncovered and never charges To Be ` +
                `Assigned — when the month turns it rides onto the card as debt rather than ` +
                `being written off. Pay it down by assigning to the card.`
              }
            >
              {formatMoney(-overspentOnCards)}
              <span className="tba-hero__chip-word">on cards</span>
            </span>
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
          <div className="tba-history-modal" role="dialog" aria-modal aria-labelledby="tba-history-title">
            <div className="tba-history-modal__header">
              <span id="tba-history-title" className="tba-history-modal__title">
                <History size={14} />
                Money moved this month
              </span>
              <button className="tba-history-modal__close" onClick={() => setDrawerOpen(false)} aria-label="Close">
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
          tba={Number(tba)}
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
            tba={Number(tba)}
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
      {showCover && (
        <CoverOverspentModal budgetId={budgetId} month={month} onClose={() => setShowCover(false)} />
      )}
    </div>
  )
}
