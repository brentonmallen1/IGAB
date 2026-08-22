import { apiErrorMessage } from '../../api/client'
import { TAB_FILTER_SUPPORT, useReportStore } from '../../stores/reportStore'

interface Props {
  onRetry: () => void
  /** The failed query's error, when the caller has it. Without one the state
   *  stays generic and assumes retrying is worth a try. */
  error?: unknown
}

/** Statuses where the same request can plausibly succeed next time: no reply
 *  at all (offline, dropped connection), a timeout, rate limiting, or a
 *  gateway that never reached the app. A 500 is the app itself raising on this
 *  input, so it will raise again — that is the case worth saying out loud. */
function isTransient(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === undefined) return true
  return status === 408 || status === 429 || status === 502 || status === 503 || status === 504
}

/** FastAPI's unhandled-exception body. Repeating it tells the user nothing. */
const BOILERPLATE = new Set(['Internal Server Error', 'Not Found', ''])

function detailOf(error: unknown): string | null {
  if (error === undefined) return null
  const message = apiErrorMessage(error, '')
  return BOILERPLATE.has(message) ? null : message
}

/**
 * Shown when a report's API query fails: styled like the loading/empty states
 * so a failed tab never silently shows "no data".
 *
 * A bare "Retry" is a lie when the server failed deterministically — the
 * button is there, the user presses it, and nothing ever changes. So the state
 * says which kind of failure this is, and when a view is driving the report it
 * offers the one action from here that can actually alter the outcome.
 */
export function ReportErrorState({ onRetry, error }: Props) {
  const activeTab = useReportStore((s) => s.activeTab)
  const viewId = useReportStore((s) => s.filters.viewId)
  const setFilters = useReportStore((s) => s.setFilters)

  const transient = isTransient(error)
  const detail = detailOf(error)
  const viewInPlay = !transient && !!viewId && !!TAB_FILTER_SUPPORT[activeTab]?.views

  return (
    <div className="report-error" role="alert">
      <p className="report-error__title">Couldn't load this report.</p>

      {detail && <p className="report-error__detail">{detail}</p>}

      {!transient && (
        <p className="report-error__hint">
          {viewInPlay
            ? 'This report is grouped by a saved view. Clearing it puts the report back on your budget’s own groups.'
            : 'Retrying sends the same request, so it will fail the same way. Changing the date range or filters may get past it.'}
        </p>
      )}

      <div className="report-error__actions">
        {viewInPlay && (
          <button
            type="button"
            className="report-error__retry report-error__retry--primary"
            onClick={() => setFilters({ viewId: null })}
          >
            Clear view
          </button>
        )}
        <button type="button" className="report-error__retry" onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  )
}
