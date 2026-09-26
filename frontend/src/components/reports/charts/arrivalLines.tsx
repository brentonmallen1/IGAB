import { ReferenceLine } from 'recharts'
import type { ArrivalMark } from '../../../utils/trackingStart'

/**
 * A dashed line at each month something began being counted, numbered to
 * match `TrackingStartNote` under the chart. Called, not rendered as a
 * component: recharts reads its reference lines from the chart's direct
 * children.
 *
 * `xOf` maps a point index to the category the chart's x axis draws there
 * (its formatted month label). Muted, because an arrival is context for the
 * lines, not a line of its own.
 */
export function arrivalLines(marks: ArrivalMark[], xOf: (index: number) => string) {
  return marks.map((m) => (
    <ReferenceLine
      key={`arrival-${m.date}`}
      x={xOf(m.index)}
      stroke="var(--text-muted)"
      strokeDasharray="2 4"
      label={{
        value: m.label,
        position: 'insideTopLeft',
        fill: 'var(--text-muted)',
        fontSize: 10,
      }}
    />
  ))
}
