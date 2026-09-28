import { createContext } from 'react'

/** True inside a pinned header's summary: `MetricCard` renders as one
 *  "LABEL value" item instead of a box — the same props, so the summary
 *  can never state a figure the box does not. */
export const MetricCompactContext = createContext(false)
