import { useMemo, useState } from 'react'
import { useAppStore } from '../../../stores/appStore'
import { useLiabilities } from '../../../api/liabilities'
import { usePayVsSave, type PayVsSaveRequest } from '../../../api/guide'
import { useFormatters } from '../../../hooks/useFormatters'
import { useDebouncedValue } from '../../../hooks/useDebouncedValue'
import { parseAmountInput } from '../../../utils/money'

/**
 * Extra money against a debt, or into savings at a rate you can get today?
 *
 * Both arms run over the months the minimum-only plan takes. The savings rate
 * is typed by the user and labelled as such: this never assumes a return.
 */
export function PayVsSave() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const { data: liabilities } = useLiabilities(budgetId)
  const [balance, setBalance] = useState('')
  const [rate, setRate] = useState('')
  const [minimum, setMinimum] = useState('')
  const [extra, setExtra] = useState('')
  const [apy, setApy] = useState('')
  const { formatMoney, formatDate } = useFormatters()

  const usable = (liabilities ?? []).filter(
    (l) => l.interest_rate !== null && l.minimum_payment !== null && l.current_balance > 0
  )

  function prefill(id: string) {
    const l = usable.find((x) => x.id === id)
    if (!l) return
    setBalance(String(l.current_balance))
    setRate(String(l.interest_rate))
    setMinimum(String(l.minimum_payment))
  }

  const parsed = useMemo(() => {
    const fields = { balance, annual_rate: rate, minimum_payment: minimum, extra, savings_apy: apy }
    const body: Partial<PayVsSaveRequest> = {}
    const bad: string[] = []
    for (const [k, v] of Object.entries(fields)) {
      if (!v.trim()) {
        bad.push(k)
        continue
      }
      const n = parseAmountInput(v)
      if (Number.isNaN(n) || n < 0) bad.push(k)
      else body[k as keyof PayVsSaveRequest] = String(n)
    }
    return { body: bad.length ? null : (body as PayVsSaveRequest), bad }
  }, [balance, rate, minimum, extra, apy])

  const settledKey = useDebouncedValue(JSON.stringify(parsed.body))
  const settledBody = useMemo(
    () => (settledKey === 'null' ? null : (JSON.parse(settledKey) as PayVsSaveRequest)),
    [settledKey]
  )
  const { data } = usePayVsSave(budgetId, settledBody)
  const invalid = (k: string) =>
    parsed.bad.includes(k) && (fields[k] ?? '').trim() ? 'is-invalid' : ''
  const fields: Record<string, string> = {
    balance,
    annual_rate: rate,
    minimum_payment: minimum,
    extra,
    savings_apy: apy,
  }

  return (
    <div className="tool">
      <div className="tool__inputs tool__grid">
        {usable.length > 0 && (
          <label className="tool__field tool__field--wide">
            <span>Start from a debt</span>
            <select defaultValue="" onChange={(e) => prefill(e.target.value)}>
              <option value="">Type the figures below…</option>
              {usable.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="tool__field">
          <span>Balance</span>
          <input
            inputMode="decimal"
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
            className={invalid('balance')}
          />
        </label>
        <label className="tool__field">
          <span>APR %</span>
          <input
            inputMode="decimal"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            className={invalid('annual_rate')}
          />
        </label>
        <label className="tool__field">
          <span>Minimum / mo</span>
          <input
            inputMode="decimal"
            value={minimum}
            onChange={(e) => setMinimum(e.target.value)}
            className={invalid('minimum_payment')}
          />
        </label>
        <label className="tool__field">
          <span>Extra / mo</span>
          <input
            inputMode="decimal"
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            className={invalid('extra')}
          />
        </label>
        <label className="tool__field">
          <span>Savings rate you can get today, %</span>
          <input
            inputMode="decimal"
            value={apy}
            onChange={(e) => setApy(e.target.value)}
            className={invalid('savings_apy')}
          />
        </label>
      </div>

      {data && (
        <div className="tool__results">
          <p className="tool__summary">
            {data.favours === 'pay' && (
              <>
                Over the {data.horizon_months} months the minimum alone takes, paying the extra
                avoids <strong>{formatMoney(Number(data.debt_interest_saved))}</strong> in interest;
                saving it would earn {formatMoney(Number(data.savings_interest_earned))}.{' '}
                <strong>Paying down wins.</strong>
              </>
            )}
            {data.favours === 'save' && (
              <>
                Over {data.horizon_months} months, saving the extra earns{' '}
                <strong>{formatMoney(Number(data.savings_interest_earned))}</strong>; paying it down
                avoids {formatMoney(Number(data.debt_interest_saved))}.{' '}
                <strong>Saving comes out ahead.</strong>
              </>
            )}
            {data.favours === 'even' && (
              <>The two come out even over {data.horizon_months} months.</>
            )}
          </p>
          <div className="tool__cards">
            <div className="tool__card">
              <h3 className="tool__card-title">Pay it down</h3>
              <dl className="tool__facts">
                <dt>Paid off</dt>
                <dd>
                  {data.pay_payoff_date ? formatDate(data.pay_payoff_date) : 'never at this pace'}
                </dd>
                <dt>Sooner by</dt>
                <dd>
                  {data.baseline_never_pays_off
                    ? 'the minimum alone never clears it'
                    : `${data.months_sooner} ${data.months_sooner === 1 ? 'month' : 'months'}`}
                </dd>
                <dt>Interest avoided</dt>
                <dd className="tabular">{formatMoney(Number(data.debt_interest_saved))}</dd>
              </dl>
            </div>
            <div className="tool__card">
              <h3 className="tool__card-title">Save it instead</h3>
              <dl className="tool__facts">
                <dt>Put aside</dt>
                <dd className="tabular">{formatMoney(Number(data.savings_contributed))}</dd>
                <dt>Grows to</dt>
                <dd className="tabular">{formatMoney(Number(data.savings_balance))}</dd>
                <dt>Interest earned</dt>
                <dd className="tabular">{formatMoney(Number(data.savings_interest_earned))}</dd>
              </dl>
            </div>
          </div>
          {data.breakeven_apy !== null && (
            <p className="tool__aside">
              Break-even: a savings rate of about{' '}
              <strong>{Number(data.breakeven_apy).toFixed(2)}%</strong> would earn what paying down
              avoids. Below that, pay the debt.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
