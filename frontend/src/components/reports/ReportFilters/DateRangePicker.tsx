import { useState } from 'react'
import { Calendar } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useReportRange } from '../../../api/reports'
import './DateRangePicker.css'
import { addMonths, currentMonthStart, today } from '../../../utils/dates'
import { monthsAgoStartISO, monthWindow, thisMonthWindow } from '../../../utils/dateWindow'

interface Props {
  startDate: string
  endDate: string
  onChange: (start: string, end: string) => void
}

interface Preset {
  label: string
  getValue: () => { start: string; end: string }
}

/** "Last N Months" is the current month and the N-1 before it, through today. */
function lastMonths(n: number): Preset {
  return {
    label: `Last ${n} Months`,
    getValue: () => ({ start: monthsAgoStartISO(n - 1), end: today() }),
  }
}

// Every preset is a dateWindow helper. The picker once kept its own
// firstOfMonth / lastOfMonth / subtractMonths beside the module that already
// does that arithmetic, and "This Month" was written twice — here and in the
// report store's default — where a drift leaves the default matching no preset.
const PRESETS: Preset[] = [
  { label: 'This Month', getValue: thisMonthWindow },
  { label: 'Last Month', getValue: () => monthWindow(addMonths(currentMonthStart(), -1)) },
  lastMonths(3),
  lastMonths(6),
  lastMonths(12),
  {
    label: 'This Year',
    getValue: () => {
      const t = today()
      return { start: `${t.slice(0, 4)}-01-01`, end: t }
    },
  },
  {
    label: 'Last Year',
    getValue: () => {
      const y = Number(today().slice(0, 4)) - 1
      return { start: `${y}-01-01`, end: `${y}-12-31` }
    },
  },
]

/** "All time" needs the budget's own history, so it cannot be a static preset
 *  like the others. Resolved to a real date here, exactly as the months-based
 *  picker resolves its own "All time" to a real month count — no sentinel
 *  travels to the server either way. */
function allTimePreset(earliestMonth: string): Preset {
  return {
    label: 'All Time',
    getValue: () => ({ start: earliestMonth, end: today() }),
  }
}

export function DateRangePicker({ startDate, endDate, onChange }: Props) {
  const [showCustom, setShowCustom] = useState(false)
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: range } = useReportRange(budgetId)
  // Absent on an empty budget, where "all time" would be an empty range.
  const presets = range?.earliest_month
    ? [...PRESETS, allTimePreset(range.earliest_month)]
    : PRESETS

  function applyPreset(preset: Preset) {
    const { start, end } = preset.getValue()
    onChange(start, end)
    setShowCustom(false)
  }

  function activePreset() {
    for (const p of presets) {
      const { start, end } = p.getValue()
      if (start === startDate && end === endDate) return p.label
    }
    return null
  }

  const active = activePreset()

  return (
    <div className="drp">
      <div className="drp__presets">
        {presets.map((p) => (
          <button
            key={p.label}
            className={`drp__preset ${active === p.label ? 'drp__preset--active' : ''}`}
            onClick={() => applyPreset(p)}
            type="button"
          >
            {p.label}
          </button>
        ))}
        <button
          className={`drp__preset drp__preset--custom ${showCustom || !active ? 'drp__preset--active' : ''}`}
          onClick={() => setShowCustom((v) => !v)}
          type="button"
        >
          <Calendar size={12} />
          Custom
        </button>
      </div>
      {(showCustom || (!active && (startDate || endDate))) && (
        <div className="drp__custom">
          <label className="drp__label">
            From
            <input
              type="date"
              className="drp__input"
              value={startDate}
              onChange={(e) => onChange(e.target.value, endDate)}
            />
          </label>
          <span className="drp__sep">–</span>
          <label className="drp__label">
            To
            <input
              type="date"
              className="drp__input"
              value={endDate}
              onChange={(e) => onChange(startDate, e.target.value)}
            />
          </label>
        </div>
      )}
    </div>
  )
}
