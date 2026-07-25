import { useMemo, useRef, useState } from 'react'
import { ChevronDown, Wand2 } from 'lucide-react'
import { useBudgetMonth } from '../../../api/budgets'
import { useCategories, useCategoryGroups } from '../../../api/categories'
import { useIsMobile } from '../../../hooks/useMediaQuery'
import { useUIStore } from '../../../stores/uiStore'
import { formatMoney } from '../../../utils/money'
import { ContextMenu, type ContextMenuItem } from '../../common/ContextMenu/ContextMenu'
import { BottomSheet } from '../../common/BottomSheet/BottomSheet'
import { AutoAssignModal } from '../AutoAssignModal/AutoAssignModal'
import { CoverOverspentModal } from './CoverOverspentModal'
import { TbaDrawer } from './TbaDrawer'
import './TbaHero.css'

interface Props {
  budgetId: string
  month: string
}

/**
 * The centerpiece of the budget page: To Be Assigned, up and center, with the
 * money-movement actions attached — assign to targets, cover overspending,
 * and a drawer holding the overspending summary and the month's move log.
 */
export function TbaHero({ budgetId, month }: Props) {
  const { data: budgetMonth } = useBudgetMonth(budgetId, month)
  const { data: categories = [] } = useCategories(budgetId)
  const { data: groups = [] } = useCategoryGroups(budgetId)
  const isMobile = useIsMobile()

  const drawerOpen = useUIStore((s) => s.tbaDrawerOpen)
  const setDrawerOpen = useUIStore((s) => s.setTbaDrawerOpen)
  const showAutoAssign = useUIStore((s) => s.isAutoAssignOpen)
  const setShowAutoAssign = useUIStore((s) => s.setAutoAssignOpen)
  const showCover = useUIStore((s) => s.isCoverOverspentOpen)
  const setShowCover = useUIStore((s) => s.setCoverOverspentOpen)
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuPos, setMenuPos] = useState({ x: 0, y: 0 })
  const assignRef = useRef<HTMLDivElement>(null)

  const tba = budgetMonth?.to_be_assigned ?? 0
  const overspent = Number(budgetMonth?.total_overspent ?? 0)
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

  const menuItems: ContextMenuItem[] = [
    { id: 'targets', label: 'Auto-assign to targets' },
    ...(overspent > 0
      ? [{ id: 'cover', label: `Cover overspending (${formatMoney(-overspent)})` }]
      : []),
  ]

  function openMenu() {
    const rect = assignRef.current?.getBoundingClientRect()
    if (rect) setMenuPos({ x: rect.left, y: rect.bottom + 4 })
    setMenuOpen(true)
  }

  function handleMenuSelect(id: string) {
    setMenuOpen(false)
    if (id === 'targets') setShowAutoAssign(true)
    if (id === 'cover') setShowCover(true)
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
      onCoverOverspent={openCoverFromDrawer}
    />
  )

  return (
    <div className="tba-hero">
      <div className="tba-hero__pill">
        <div className="tba-hero__info">
          <span className="tba-hero__label">To Be Assigned</span>
          <span className={`tba-hero__amount ${tbaClass}`}>{formatMoney(tba)}</span>
        </div>

        <div className="tba-hero__actions">
          <div className="tba-hero__assign" ref={assignRef}>
            <button
              className="tba-hero__assign-main"
              onClick={() => setShowAutoAssign(true)}
              title="Auto-assign to targets"
            >
              <Wand2 size={13} />
              Assign
            </button>
            <button
              className="tba-hero__assign-caret"
              onClick={openMenu}
              aria-label="More assign actions"
              aria-haspopup="menu"
            >
              <ChevronDown size={14} />
            </button>
          </div>

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

      {menuOpen && (
        <ContextMenu
          items={menuItems}
          onSelect={handleMenuSelect}
          onClose={() => setMenuOpen(false)}
          position={menuPos}
        />
      )}

      {showAutoAssign && (
        <AutoAssignModal budgetId={budgetId} month={month} onClose={() => setShowAutoAssign(false)} />
      )}
      {showCover && (
        <CoverOverspentModal budgetId={budgetId} month={month} onClose={() => setShowCover(false)} />
      )}
    </div>
  )
}
