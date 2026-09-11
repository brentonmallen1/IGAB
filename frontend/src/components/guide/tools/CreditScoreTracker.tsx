import { useMemo, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useAppStore } from '../../../stores/appStore'
import {
  useCreateCreditScore,
  useCreditScores,
  useDeleteCreditScore,
} from '../../../api/creditScores'
import { useFormatters } from '../../../hooks/useFormatters'
import { today } from '../../../utils/dates'
import { apiErrorMessage } from '../../../api/client'

const BUREAUS = [
  { value: '', label: 'Any / not sure' },
  { value: 'equifax', label: 'Equifax' },
  { value: 'experian', label: 'Experian' },
  { value: 'transunion', label: 'TransUnion' },
]

/**
 * Scores you look up yourself, typed in by date and drawn over time. Nothing
 * is fetched: there is no API a household should wire a bureau into, and the
 * number you saw is the number kept.
 */
export function CreditScoreTracker() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { formatDate } = useFormatters()
  const { data: scores = [] } = useCreditScores(budgetId)
  const create = useCreateCreditScore(budgetId ?? '')
  const remove = useDeleteCreditScore(budgetId ?? '')
  const [recordedOn, setRecordedOn] = useState(today())
  const [score, setScore] = useState('')
  const [bureau, setBureau] = useState('')
  const [source, setSource] = useState('')
  const [error, setError] = useState<string | null>(null)

  const chartData = useMemo(
    () => scores.map((s) => ({ date: formatDate(s.recorded_on), score: s.score })),
    [scores, formatDate]
  )
  const latest = scores[scores.length - 1]

  async function add(e: React.FormEvent) {
    e.preventDefault()
    const n = Number(score)
    if (!Number.isInteger(n) || n < 300 || n > 900) {
      setError('Enter a score between 300 and 900.')
      return
    }
    setError(null)
    try {
      await create.mutateAsync({
        recorded_on: recordedOn,
        score: n,
        bureau: bureau || null,
        source: source.trim() || null,
      })
      setScore('')
      setSource('')
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save that score'))
    }
  }

  return (
    <div className="tool">
      <form className="tool__inputs tool__grid" onSubmit={add}>
        <label className="tool__field">
          <span>Date</span>
          <input type="date" value={recordedOn} onChange={(e) => setRecordedOn(e.target.value)} />
        </label>
        <label className="tool__field">
          <span>Score</span>
          <input
            type="number"
            inputMode="numeric"
            min="300"
            max="900"
            step="1"
            value={score}
            onChange={(e) => setScore(e.target.value)}
            placeholder="742"
            required
          />
        </label>
        <label className="tool__field">
          <span>Bureau</span>
          <select value={bureau} onChange={(e) => setBureau(e.target.value)}>
            {BUREAUS.map((b) => (
              <option key={b.value} value={b.value}>
                {b.label}
              </option>
            ))}
          </select>
        </label>
        <label className="tool__field">
          <span>Where you saw it</span>
          <input
            type="text"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="Card issuer dashboard, annual report…"
          />
        </label>
        <div className="tool__field tool__field--inline">
          <button type="submit" className="tool__add" disabled={create.isPending}>
            {create.isPending ? 'Saving…' : 'Add score'}
          </button>
          {error && (
            <span className="tool__error" role="alert">
              {error}
            </span>
          )}
        </div>
      </form>

      {scores.length === 0 ? (
        <p className="tool__hint">
          No scores yet. Look one up and type it in — the line builds from here.
        </p>
      ) : (
        <div className="tool__results">
          <p className="tool__summary">
            Latest: <strong>{latest.score}</strong>
            {latest.bureau ? ` (${latest.bureau})` : ''} on {formatDate(latest.recorded_on)}
          </p>
          <div className="tool__chart" style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
                <XAxis dataKey="date" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                <YAxis
                  domain={[300, 850]}
                  // A credit score, not money: its own unit, left unmasked.
                  tickFormatter={(score: number) => String(score)}
                  tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--surface-overlay)',
                    border: '1px solid var(--edge)',
                    color: 'var(--text-primary)',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="var(--color-accent)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="tool__table">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Score</th>
                <th scope="col">Bureau</th>
                <th scope="col">Source</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {[...scores].reverse().map((s) => (
                <tr key={s.id}>
                  <td>{formatDate(s.recorded_on)}</td>
                  <td>{s.score}</td>
                  <td>{s.bureau ?? '—'}</td>
                  <td>{s.source ?? '—'}</td>
                  <td className="tool__row-actions">
                    <button
                      type="button"
                      className="tool__icon-button"
                      onClick={() => remove.mutate(s.id)}
                      aria-label={`Remove the score from ${formatDate(s.recorded_on)}`}
                      title="Remove"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="tool__hint">
        Where to look one up: your card issuer&apos;s dashboard usually shows a score for free; in
        the US,{' '}
        <a href="https://www.annualcreditreport.com" target="_blank" rel="noreferrer">
          AnnualCreditReport.com
        </a>{' '}
        gives the full report from{' '}
        <a href="https://www.equifax.com" target="_blank" rel="noreferrer">
          Equifax
        </a>
        ,{' '}
        <a href="https://www.experian.com" target="_blank" rel="noreferrer">
          Experian
        </a>{' '}
        and{' '}
        <a href="https://www.transunion.com" target="_blank" rel="noreferrer">
          TransUnion
        </a>
        . Under 30% utilization on each card and no missed payments move it most.
      </p>
    </div>
  )
}
