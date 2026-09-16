/** The emergency fund "Setting money aside" shows a Counting line for:
 * invented, with the shared example names. Drawn by the real
 * `EmergencyFundCountingView`, so the example reads exactly as the reports do. */
import type { EmergencyFund } from '../../../types'

export const EXAMPLE_FUND: EmergencyFund = {
  set_up: true,
  total: 9400,
  categories: [{ id: 'example-fund', name: 'Emergency Fund', balance: 2400 }],
  accounts: [{ id: 'example-reserve', name: 'Harborstone Reserve', balance: 6000 }],
  external: { declared: true, amount: 1000, as_of: null, note: null },
}
