import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAppStore } from '../../../stores/appStore'
import { useEmergencyFundPlan, useGuideOverview } from '../../../api/guide'
import { useFormatters } from '../../../hooks/useFormatters'
import { useDebouncedValue } from '../../../hooks/useDebouncedValue'
import { parseAmountInput } from '../../../utils/money'
import { otherFigureNote } from '../../../utils/essentialsFigures'
import { SpreadSinkingFundsToggle } from '../../common/SpreadSinkingFundsToggle/SpreadSinkingFundsToggle'
import { EmergencyFundCounting } from '../../emergencyFund/EmergencyFundCounting'

/**
 * Months of essential spending, from the roadmap's own figures.
 *
 * A thin tool: the essentials and emergency-fund numbers are the ones the
 * roadmap shows (including anything declared as held elsewhere), and the
 * only arithmetic is months × essentials, the gap, and how long the gap
 * takes at what you put aside — all served, none re-derived here.
 *
 * Essentials is the 90-day figure with yearly Long-term expense bills spread
 * over twelve months when the budget's setting is on; the toggle is here
 * because the target moves with it, and the other figure is named beside it.
 */
export function EmergencyFundSizer() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: overview } = useGuideOverview(budgetId)
  const low = overview?.thresholds.emergency_fund_months ?? 3
  const high = overview?.thresholds.emergency_fund_months_high ?? 6
  const [months, setMonths] = useState(low)
  const [contribution, setContribution] = useState('')
  const { formatMoney, formatDate } = useFormatters()

  const parsedContribution = useMemo(() => {
    if (!contribution.trim()) return { value: '0', bad: false }
    const n = parseAmountInput(contribution)
    return Number.isNaN(n) || n < 0 ? { value: '0', bad: true } : { value: String(n), bad: false }
  }, [contribution])

  const settled = useDebouncedValue(parsedContribution.value)
  const body = useMemo(() => ({ months, monthly_contribution: settled }), [months, settled])
  const { data } = useEmergencyFundPlan(budgetId, body)
  const other = otherFigureNote(data?.essentials, formatMoney)

  return (
    <div className="tool">
      <div className="tool__inputs tool__grid">
        <label className="tool__field tool__field--wide">
          <span>
            Months of essential spending: <strong>{months}</strong>
            <span className="tool__hint">
              {' '}
              (the roadmap suggests {low}–{high})
            </span>
          </span>
          <input
            type="range"
            min={1}
            max={12}
            step={1}
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            list="ef-marks"
          />
          <datalist id="ef-marks">
            <option value={low} />
            <option value={high} />
          </datalist>
        </label>
        <label className="tool__field">
          <span>You can put aside each month</span>
          <input
            inputMode="decimal"
            value={contribution}
            onChange={(e) => setContribution(e.target.value)}
            className={parsedContribution.bad ? 'is-invalid' : ''}
            placeholder="0"
          />
        </label>
      </div>

      <SpreadSinkingFundsToggle budgetId={budgetId} />

      {data && (
        <div className="tool__results">
          <dl className="tool__facts tool__facts--wide">
            <dt>Essential spending, per month</dt>
            <dd className="tabular">
              {data.essentials !== null ? (
                <>
                  {formatMoney(data.essentials.monthly)}
                  {other && <span className="tool__hint"> ({other})</span>}
                </>
              ) : (
                <>
                  not known yet —{' '}
                  <Link to="/reports?tab=essentials">
                    tag what you could not do without as Essential
                  </Link>
                </>
              )}
            </dd>
            <dt>
              Target, {data.months} {data.months === 1 ? 'month' : 'months'}
            </dt>
            <dd className="tabular">
              {data.target !== null ? formatMoney(Number(data.target)) : '—'}
            </dd>
            <dt>Emergency fund today</dt>
            <dd>
              {data.current !== null && (
                <span className="tabular">{formatMoney(Number(data.current))}</span>
              )}
              {budgetId && <EmergencyFundCounting budgetId={budgetId} />}
            </dd>
            <dt>Still to save</dt>
            <dd className="tabular">{data.gap !== null ? formatMoney(Number(data.gap)) : '—'}</dd>
            <dt>Funded by</dt>
            <dd>
              {data.months_to_fund === 0 && 'already there'}
              {data.months_to_fund !== null && data.months_to_fund > 0 && data.funded_by && (
                <>
                  {formatDate(data.funded_by)} — {data.months_to_fund}{' '}
                  {data.months_to_fund === 1 ? 'month' : 'months'} at{' '}
                  {formatMoney(Number(data.monthly_contribution))} a month
                </>
              )}
              {data.months_to_fund === null &&
                data.gap !== null &&
                Number(data.gap) > 0 &&
                'put a monthly amount above to see a date'}
              {data.months_to_fund === null && data.gap === null && '—'}
            </dd>
          </dl>
        </div>
      )}
    </div>
  )
}
