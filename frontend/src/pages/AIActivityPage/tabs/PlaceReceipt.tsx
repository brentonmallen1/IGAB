import { useMemo } from 'react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../../api/accounts'
import { usePlaceReceipt, type AIJob, type PlaceTarget } from '../../../api/aiJobs'
import { apiErrorMessage } from '../../../api/client'
import { Combobox, type ComboboxOption } from '../../../components/common/Combobox/Combobox'
import { useFormatters } from '../../../hooks/useFormatters'
import { accountNameMap, openAccounts } from '../../../utils/accountLists'
import { parseApiDecimal } from '../../../utils/money'
import './PlaceReceipt.css'

/**
 * A receipt scanned with no account, waiting for one.
 *
 * Nothing has moved yet — no transaction exists — and the row says so, then
 * offers the best answer it has: the bank's own row for this purchase, if it
 * has arrived (the receipt goes ON that row instead of beside it as a
 * duplicate), or the account whose card paid, if that ending is on file.
 * Either way a person can choose any open account instead.
 */
export function PlaceReceipt({ job, budgetId }: { job: AIJob; budgetId: string }) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const place = usePlaceReceipt(budgetId)
  const { formatMoney, formatDayMonth } = useFormatters()
  const names = useMemo(() => accountNameMap(accounts), [accounts])
  const options = useMemo<ComboboxOption[]>(
    () =>
      openAccounts(accounts).map((a) => ({
        id: a.id,
        label: a.name,
        group: a.on_budget ? '' : 'Tracking',
      })),
    [accounts]
  )

  function go(target: PlaceTarget, where: string) {
    place.mutate(
      { jobId: job.id, ...target },
      {
        onSuccess: () => toast.success(`Receipt put in ${where}`),
        onError: (err) => toast.error(apiErrorMessage(err, 'Could not place the receipt')),
      }
    )
  }

  const match = job.bank_match
  const last4 = job.result?.draft?.card_last4
  const cardOwner = job.card_ending_account_id

  return (
    <div className="place-receipt">
      <p className="place-receipt__lede">Not in your budget yet — choose where it goes.</p>
      <div className="place-receipt__choices">
        {match ? (
          <button
            type="button"
            className="place-receipt__primary"
            disabled={place.isPending}
            onClick={() =>
              go({ transaction_id: match.id }, names.get(match.account_id) ?? 'that charge')
            }
          >
            Put it on the {formatMoney(parseApiDecimal(match.amount))} charge in{' '}
            {names.get(match.account_id) ?? 'another account'} on {formatDayMonth(match.date)}
          </button>
        ) : cardOwner ? (
          <button
            type="button"
            className="place-receipt__primary"
            disabled={place.isPending}
            onClick={() => go({ account_id: cardOwner }, names.get(cardOwner) ?? 'that account')}
          >
            Put it in {names.get(cardOwner) ?? 'the account'}
            {last4 ? ` (card ending ${last4})` : ''}
          </button>
        ) : null}
        <span className="place-receipt__picker">
          <Combobox
            value={null}
            options={options}
            onChange={(id) => id && go({ account_id: id }, names.get(id) ?? 'that account')}
            placeholder="Choose an account…"
            aria-label="Put this receipt in an account"
          />
        </span>
      </div>
    </div>
  )
}
