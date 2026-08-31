import { useState } from 'react'
import { useUpdateSimpleFINConnection } from '../../../api/simplefin'
import { useFormatters } from '../../../hooks/useFormatters'
import type { SimpleFINConnection } from '../../../types'
import {
  INTERVAL_CHOICES,
  deriveInterval,
  hoursForInterval,
  localHourToUtcHour,
  utcHourToLocalHour,
} from './hourSchedule'
import './SyncSchedule.css'

type Mode = 'off' | 'interval' | 'times'

function modeFor(hours: number[]): Mode {
  if (hours.length === 0) return 'off'
  return deriveInterval(hours) !== null ? 'interval' : 'times'
}

/**
 * When a bank connection syncs itself.
 *
 * Two ways to say it — "every N hours" and a set of times — writing the one
 * field the server actually stores. The times are picked in local time
 * because that is what a person means by "overnight"; UTC is what gets
 * stored, and the two caveats that follow from that are printed rather than
 * left to be discovered.
 */
export function SyncSchedule({ connection }: { connection: SimpleFINConnection }) {
  const update = useUpdateSimpleFINConnection()
  const { formatTime } = useFormatters()
  const offsetMinutes = new Date().getTimezoneOffset()

  const hours = connection.sync_hours ?? []
  const [mode, setMode] = useState<Mode>(() => modeFor(hours))
  const derived = deriveInterval(hours)
  const [every, setEvery] = useState<number>(derived ?? 6)
  const [anchor, setAnchor] = useState<number>(
    hours.length > 0 ? utcHourToLocalHour(Math.min(...hours), offsetMinutes) : 0
  )

  function save(next: number[]) {
    update.mutate({ id: connection.id, sync_hours: next })
  }

  function chooseMode(next: Mode) {
    setMode(next)
    if (next === 'off') save([])
    if (next === 'interval')
      save(hoursForInterval(every, localHourToUtcHour(anchor, offsetMinutes)))
    // 'times' keeps whatever is set; the user picks from here
  }

  function setInterval(nextEvery: number, nextAnchor: number) {
    setEvery(nextEvery)
    setAnchor(nextAnchor)
    save(hoursForInterval(nextEvery, localHourToUtcHour(nextAnchor, offsetMinutes)))
  }

  function toggleHour(localHour: number) {
    const utc = localHourToUtcHour(localHour, offsetMinutes)
    const next = hours.includes(utc) ? hours.filter((h) => h !== utc) : [...hours, utc]
    save(next.sort((a, b) => a - b))
  }

  /** A stored UTC hour, as it reads on this clock. */
  function localLabel(utcHour: number): string {
    const d = new Date()
    d.setUTCHours(utcHour, 0, 0, 0)
    return formatTime(d.getHours(), d.getMinutes())
  }

  return (
    <div className="sync-schedule">
      <div className="settings-row">
        <div>
          <div className="settings-row__label">Automatic sync</div>
          <div className="settings-row__desc">
            When this connection syncs on its own. Syncs run on the hour.
          </div>
        </div>
        <select
          className="settings-select"
          value={mode}
          onChange={(e) => chooseMode(e.target.value as Mode)}
        >
          <option value="off">Never</option>
          <option value="interval">Every few hours</option>
          <option value="times">At set times</option>
        </select>
      </div>

      {mode === 'interval' && (
        <div className="settings-row">
          <div>
            <div className="settings-row__label">How often</div>
            <div className="settings-row__desc">Starting from the first sync of the day</div>
          </div>
          <div className="sync-schedule__interval">
            <select
              className="settings-select"
              value={every}
              aria-label="Sync every"
              onChange={(e) => setInterval(Number(e.target.value), anchor)}
            >
              {INTERVAL_CHOICES.map((n) => (
                <option key={n} value={n}>
                  Every {n} hours
                </option>
              ))}
            </select>
            <select
              className="settings-select"
              value={anchor}
              aria-label="First sync at"
              onChange={(e) => setInterval(every, Number(e.target.value))}
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  from {formatTime(h, 0)}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      {mode === 'times' && (
        <div className="sync-schedule__times">
          <div className="settings-row__desc sync-schedule__times-label">
            Pick the hours to sync at — your local time.
          </div>
          <div className="sync-schedule__grid" role="group" aria-label="Sync hours">
            {Array.from({ length: 24 }, (_, localHour) => {
              const utc = localHourToUtcHour(localHour, offsetMinutes)
              const on = hours.includes(utc)
              return (
                <button
                  key={localHour}
                  type="button"
                  className={`sync-schedule__hour ${on ? 'sync-schedule__hour--on' : ''}`}
                  aria-pressed={on}
                  onClick={() => toggleHour(localHour)}
                >
                  {formatTime(localHour, 0)}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {hours.length > 0 && (
        <div className="sync-schedule__summary">
          Syncs at {hours.map(localLabel).join(', ')} your time.
          {/* Both caveats of storing a UTC hour, said once, where the choice
              is made rather than discovered an hour late in November. */}
          <span className="sync-schedule__caveat">
            {' '}
            Times are stored in UTC, so they shift by an hour when daylight saving changes.
          </span>
        </div>
      )}
    </div>
  )
}
