import { useState } from 'react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../api/accounts'
import { useBudgetMonth } from '../../api/budgets'
import { useLiabilities } from '../../api/liabilities'
import { useCreateTransaction } from '../../api/transactions'
import { useFormatters } from '../../hooks/useFormatters'
import { currentMonthStart, today } from '../../utils/dates'
import { isCashAccount } from '../../utils/accountKinds'
import { parseAmountInput } from '../../utils/money'
import { AmountInput } from '../common/AmountInput/AmountInput'
import { Dialog } from '../common/Dialog/Dialog'
import './CardPaymentModal.css'

interface Props {
  budgetId: string
  /** The card being paid. */
  accountId: string
  onClose: () => void
}

/**
 * Record a payment: a TRANSFER from a cash account to a card or a loan.
 *
 * For a card, only a paired transfer from cash spends the set-aside
 * (`CARD_PAYMENT_FROM_CASH`) — a payment typed as a plain deposit lowers the
 * balance while "Ready to pay" stands still. The prefill is the served
 * `set_aside`, with the served minimum and the full balance as alternatives.
 *
 * For a loan (an off-budget liability account), the same transfer is the
 * whole story, plus one field: "extra to principal". The extra needs no
 * special handling on the server — interest is a function of the balance and
 * the clock, so everything a payment carries above this month's interest IS
 * principal — the field exists so a curtailment is one decision at record
 * time rather than mental arithmetic, and the note quotes the served
 * `monthly_interest_now` so the split is visible.
 *
 * Either way the POST goes from the CASH side: `_create_transfer` writes
 * −|amount| on `account_id` and +|amount| on `transfer_account_id`, so the
 * supply account must be the source. Both legs land in one undo batch.
 */
export function CardPaymentModal({ budgetId, accountId, onClose }: Props) {
  const { formatMoney } = useFormatters()
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const { data: monthData } = useBudgetMonth(budgetId, currentMonthStart())
  const createTxn = useCreateTransaction(budgetId)

  const card = accounts.find((a) => a.id === accountId)
  const cardStatus = monthData?.cards?.find((c) => c.account_id === accountId)
  const liability = liabilities.find((l) => l.linked_account_id === accountId)
  // A loan is an off-budget liability account; a card is on-budget.
  const isLoan = !!card && !card.on_budget

  // useAccounts already excludes closed accounts.
  const supplyAccounts = accounts.filter((a) => isCashAccount(a))

  const readyToPay = !isLoan && cardStatus && cardStatus.set_aside > 0 ? cardStatus.set_aside : null
  const fullBalance = card && card.balance < 0 ? -card.balance : null
  const minimum = liability?.minimum_payment_due_now ?? null

  const [supplyId, setSupplyId] = useState(() => supplyAccounts[0]?.id ?? '')
  const [amount, setAmount] = useState(() => {
    if (isLoan) return minimum !== null && minimum > 0 ? minimum.toFixed(2) : ''
    return readyToPay !== null ? readyToPay.toFixed(2) : (fullBalance?.toFixed(2) ?? '')
  })
  const [extra, setExtra] = useState('')
  const [error, setError] = useState<string | null>(null)

  const presets = [
    readyToPay !== null && { label: 'Ready to pay', value: readyToPay },
    minimum !== null && minimum > 0 && { label: 'Minimum', value: minimum },
    fullBalance !== null && { label: 'Full balance', value: fullBalance },
  ].filter((p): p is { label: string; value: number } => !!p)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const value = parseAmountInput(amount)
    if (isNaN(value) || value <= 0) {
      setError('Enter an amount greater than zero')
      return
    }
    const extraParsed = extra ? parseAmountInput(extra) : 0
    const extraValue = !isNaN(extraParsed) && extraParsed > 0 ? extraParsed : 0
    const total = value + extraValue
    if (!supplyId) {
      setError('Pick the account the payment comes from')
      return
    }
    setError(null)
    try {
      // One transfer for payment + extra, because that is what actually
      // happens at the bank: one debit, of which everything above the
      // month's interest reduces principal.
      await createTxn.mutateAsync({
        account_id: supplyId,
        date: today(),
        amount: -Math.abs(total),
        transfer_account_id: accountId,
        cleared: 'uncleared',
        approved: true,
      })
      toast.success(
        extraValue > 0
          ? `Payment of ${formatMoney(total)} recorded — ${formatMoney(extraValue)} of it straight to principal`
          : `Payment of ${formatMoney(value)} recorded`
      )
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Could not record the payment')
    }
  }

  if (!card) return null

  return (
    <Dialog title={`Pay ${card.name}`} onClose={onClose} historyKey="card-payment">
      <form className="card-payment" onSubmit={handleSubmit}>
        <label className="card-payment__field">
          <span>From</span>
          <select
            className="card-payment__select"
            value={supplyId}
            onChange={(e) => setSupplyId(e.target.value)}
          >
            {supplyAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} — {formatMoney(a.balance)}
              </option>
            ))}
          </select>
        </label>

        <label className="card-payment__field">
          <span>Amount</span>
          <AmountInput
            value={amount}
            onValueChange={setAmount}
            className="card-payment__amount"
            autoFocus
          />
        </label>

        {presets.length > 0 && (
          <div className="card-payment__presets" role="group" aria-label="Suggested amounts">
            {presets.map((p) => (
              <button
                key={p.label}
                type="button"
                className="card-payment__preset"
                onClick={() => setAmount(p.value.toFixed(2))}
              >
                {p.label} · {formatMoney(p.value)}
              </button>
            ))}
          </div>
        )}

        {isLoan && (
          <label className="card-payment__field">
            <span>Extra to principal (optional)</span>
            <AmountInput
              value={extra}
              onValueChange={setExtra}
              className="card-payment__amount"
              placeholder="0"
            />
          </label>
        )}

        {isLoan ? (
          <p className="card-payment__note">
            One transfer covers both. Interest accrues on the balance
            {liability?.monthly_interest_now != null &&
              ` (about ${formatMoney(liability.monthly_interest_now)} this month)`}
            , so everything above it — the extra included — reduces principal.
          </p>
        ) : (
          <p className="card-payment__note">
            Recorded as a transfer, so it spends this card&apos;s reserve — a plain deposit would
            lower the balance while Ready to pay stood still.
          </p>
        )}

        {error && <p className="card-payment__error">{error}</p>}

        <div className="card-payment__actions">
          <button type="button" className="card-payment__cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="card-payment__submit" disabled={createTxn.isPending}>
            {createTxn.isPending ? 'Recording…' : 'Record payment'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}
