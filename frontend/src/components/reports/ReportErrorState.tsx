interface Props {
  onRetry: () => void
}

/** Shown when a report's API query fails: message + retry, styled like the
 * loading/empty states so a failed tab never silently shows "no data". */
export function ReportErrorState({ onRetry }: Props) {
  return (
    <div className="report-error" role="alert">
      <p>Couldn't load this report.</p>
      <button type="button" className="report-error__retry" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}
