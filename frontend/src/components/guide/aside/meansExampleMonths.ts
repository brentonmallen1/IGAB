/**
 * Twelve invented months for the Means trend example, oldest first. Round
 * figures a reader can check: a three-paycheck month in March, a yearly bill
 * in August, and a household that ends the year keeping about an eighth of
 * what comes in. Read by the real `meansTrend()`; nobody's budget.
 */
import type { MeansMonthFigures } from '../../reports/livingMeans'

export const MEANS_EXAMPLE_MONTHS: readonly MeansMonthFigures[] = [
  { month: '2025-01-01', income: 6000, outflows: 5800 },
  { month: '2025-02-01', income: 6000, outflows: 6200 },
  { month: '2025-03-01', income: 9000, outflows: 7200 },
  { month: '2025-04-01', income: 6000, outflows: 5400 },
  { month: '2025-05-01', income: 6000, outflows: 6600 },
  { month: '2025-06-01', income: 6000, outflows: 5100 },
  { month: '2025-07-01', income: 6000, outflows: 5250 },
  { month: '2025-08-01', income: 6000, outflows: 8400 },
  { month: '2025-09-01', income: 6000, outflows: 5100 },
  { month: '2025-10-01', income: 6000, outflows: 5280 },
  { month: '2025-11-01', income: 6000, outflows: 5400 },
  { month: '2025-12-01', income: 6000, outflows: 5160 },
]
