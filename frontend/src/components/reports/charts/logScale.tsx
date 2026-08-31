// Shared log-scale toggle for report charts whose values are strictly
// positive. Real budgets span orders of magnitude — a $250k mortgage
// flattens an $855 payment plan on a linear axis; log scale lets both
// series show their shape. Charts that can carry negative values (net
// worth, composition, income-vs-expense net) must stay linear: a log axis
// cannot represent zero or sign changes.

interface LogAxisProps {
  scale?: 'log'
  domain?: [number, 'auto']
  allowDataOverflow?: boolean
}

/** Spread into the value axis: `<YAxis {...logAxisProps(logScale)} />`.
 * The domain floor of 1 keeps the axis finite when a series touches zero —
 * log(0) would otherwise blow up the scale. */
export function logAxisProps(enabled: boolean): LogAxisProps {
  if (!enabled) return {}
  return { scale: 'log', domain: [1, 'auto'], allowDataOverflow: true }
}

export function LogScaleToggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className={`report-btn ${enabled ? 'report-btn--active' : ''}`}
      onClick={onToggle}
      title="Logarithmic scale — compares values across orders of magnitude"
      aria-pressed={enabled}
    >
      Log
    </button>
  )
}
