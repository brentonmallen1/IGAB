import { useState } from 'react'
import { Calendar } from 'lucide-react'
import './DateRangePicker.css'

interface Props {
  startDate: string
  endDate: string
  onChange: (start: string, end: string) => void
}

interface Preset {
  label: string
  getValue: () => { start: string; end: string }
}

function toISO(d: Date) {
  return d.toISOString().slice(0, 10)
}

function firstOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function lastOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0)
}

function subtractMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() - n, 1)
}

const PRESETS: Preset[] = [
  {
    label: 'This Month',
    getValue: () => {
      const today = new Date()
      return { start: toISO(firstOfMonth(today)), end: toISO(today) }
    },
  },
  {
    label: 'Last Month',
    getValue: () => {
      const today = new Date()
      const prev = subtractMonths(today, 1)
      return { start: toISO(prev), end: toISO(lastOfMonth(prev)) }
    },
  },
  {
    label: 'Last 3 Months',
    getValue: () => {
      const today = new Date()
      return { start: toISO(subtractMonths(today, 2)), end: toISO(today) }
    },
  },
  {
    label: 'Last 6 Months',
    getValue: () => {
      const today = new Date()
      return { start: toISO(subtractMonths(today, 5)), end: toISO(today) }
    },
  },
  {
    label: 'Last 12 Months',
    getValue: () => {
      const today = new Date()
      return { start: toISO(subtractMonths(today, 11)), end: toISO(today) }
    },
  },
  {
    label: 'This Year',
    getValue: () => {
      const today = new Date()
      return { start: `${today.getFullYear()}-01-01`, end: toISO(today) }
    },
  },
  {
    label: 'Last Year',
    getValue: () => {
      const y = new Date().getFullYear() - 1
      return { start: `${y}-01-01`, end: `${y}-12-31` }
    },
  },
]

export function DateRangePicker({ startDate, endDate, onChange }: Props) {
  const [showCustom, setShowCustom] = useState(false)

  function applyPreset(preset: Preset) {
    const { start, end } = preset.getValue()
    onChange(start, end)
    setShowCustom(false)
  }

  function activePreset() {
    for (const p of PRESETS) {
      const { start, end } = p.getValue()
      if (start === startDate && end === endDate) return p.label
    }
    return null
  }

  const active = activePreset()

  return (
    <div className="drp">
      <div className="drp__presets">
        {PRESETS.map((p) => (
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
