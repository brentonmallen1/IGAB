/**
 * A recorded card payment has to reach the bill reminder.
 *
 * The reminder lets go when the card's served `last_payment_date` moves past
 * the last due date (`utils/paymentDue.ts`). That field rides on the
 * liabilities listing, which no transaction write used to stale — so a
 * payment typed in the register left "Sapphire Visa is due in 3 days" on
 * every page until the listing happened to refetch.
 */
import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import { invalidateAfterTransactionChange } from './invalidateAfterTransactionChange'
import { ROOT } from './queryKeys'

describe('invalidateAfterTransactionChange', () => {
  it('stales the liabilities listing, where a card payment date is served', async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries').mockResolvedValue(undefined)

    await invalidateAfterTransactionChange(qc, { budgetId: 'b1', accountId: 'a1' })

    const keys = spy.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
    expect(keys).toContain(JSON.stringify([ROOT.liabilities, 'b1']))
  })
})
