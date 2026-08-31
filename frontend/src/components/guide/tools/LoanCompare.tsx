import { useMemo, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { useAppStore } from '../../../stores/appStore'
import { useLoanCompare, type LoanCompareRequest, type LoanIn } from '../../../api/guide'
import { useFormatters } from '../../../hooks/useFormatters'
import { useDebouncedValue } from '../../../hooks/useDebouncedValue'
import { parseAmountInput } from '../../../utils/money'

interface LoanRow {
  key: number
  name: string
  principal: string
  rate: string
  term: string
  payment: string
  fees: string
}

let counter = 0
function blank(name: string): LoanRow {
  counter += 1
  return { key: counter, name, principal: '', rate: '', term: '', payment: '', fees: '' }
}

/** Two or more loans side by side. A term gives the payment; a payment gives
 *  the term. Fees count toward the total cost, which is what "cheaper" means. */
export function LoanCompare() {
  const budgetId = useAppStore((s) => s.currentBudgetId)
  const [rows, setRows] = useState<LoanRow[]>(() => [blank('Loan A'), blank('Loan B')])
  const { formatMoney, formatDate } = useFormatters()

  const parsed = useMemo(() => {
    const loans: LoanIn[] = []
    const bad = new Set<number>()
    for (const r of rows) {
      const principal = parseAmountInput(r.principal)
      const rate = parseAmountInput(r.rate)
      const term = r.term.trim() ? Number(r.term) : null
      const payment = r.payment.trim() ? parseAmountInput(r.payment) : null
      const fees = r.fees.trim() ? parseAmountInput(r.fees) : 0
      const termBad = term !== null && (!Number.isInteger(term) || term < 1)
      const paymentBad = payment !== null && (Number.isNaN(payment) || payment < 0)
      if (
        !r.name.trim() ||
        Number.isNaN(principal) ||
        principal < 0 ||
        Number.isNaN(rate) ||
        rate < 0 ||
        rate > 100 ||
        Number.isNaN(fees) ||
        fees < 0 ||
        termBad ||
        paymentBad ||
        (term === null && payment === null)
      ) {
        bad.add(r.key)
        continue
      }
      loans.push({
        name: r.name.trim(),
        principal: String(principal),
        annual_rate: String(rate),
        term_months: term,
        payment: payment === null ? null : String(payment),
        fees: String(fees),
      })
    }
    const body: LoanCompareRequest | null = bad.size === 0 && loans.length > 0 ? { loans } : null
    return { body, bad }
  }, [rows])

  const settledKey = useDebouncedValue(JSON.stringify(parsed.body))
  const settledBody = useMemo(
    () => (settledKey === 'null' ? null : (JSON.parse(settledKey) as LoanCompareRequest)),
    [settledKey]
  )
  const { data } = useLoanCompare(budgetId, settledBody)

  function update(key: number, field: keyof LoanRow, value: string) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, [field]: value } : r)))
  }
  const touched = (r: LoanRow) => r.principal || r.rate || r.term || r.payment || r.fees

  return (
    <div className="tool">
      <div className="tool__inputs">
        <table className="tool__table">
          <thead>
            <tr>
              <th>Loan</th>
              <th>Amount</th>
              <th>APR %</th>
              <th>Term, months</th>
              <th>or payment / mo</th>
              <th>Fees</th>
              <th aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const bad = parsed.bad.has(r.key) && touched(r) ? 'is-invalid' : ''
              return (
                <tr key={r.key} className={bad}>
                  <td>
                    <input
                      aria-label="Loan name"
                      value={r.name}
                      onChange={(e) => update(r.key, 'name', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="Amount"
                      inputMode="decimal"
                      value={r.principal}
                      onChange={(e) => update(r.key, 'principal', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="APR"
                      inputMode="decimal"
                      value={r.rate}
                      onChange={(e) => update(r.key, 'rate', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="Term in months"
                      inputMode="numeric"
                      value={r.term}
                      onChange={(e) => update(r.key, 'term', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="Payment per month"
                      inputMode="decimal"
                      value={r.payment}
                      onChange={(e) => update(r.key, 'payment', e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      aria-label="Fees"
                      inputMode="decimal"
                      value={r.fees}
                      onChange={(e) => update(r.key, 'fees', e.target.value)}
                      placeholder="0"
                    />
                  </td>
                  <td>
                    {rows.length > 1 && (
                      <button
                        type="button"
                        className="tool__icon-button"
                        onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}
                        aria-label={`Remove ${r.name}`}
                      >
                        <X size={13} />
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {rows.length < 6 && (
          <button
            type="button"
            className="guide-link-button tool__add"
            onClick={() =>
              setRows((rs) => [...rs, blank(`Loan ${String.fromCharCode(65 + rs.length)}`)])
            }
          >
            <Plus size={12} aria-hidden /> Add a loan
          </button>
        )}
      </div>

      {data && (
        <div className="tool__results">
          <table className="tool__table tool__table--results">
            <thead>
              <tr>
                <th>Loan</th>
                <th>Payment / mo</th>
                <th>Paid off</th>
                <th>Total interest</th>
                <th>Total cost</th>
              </tr>
            </thead>
            <tbody>
              {data.loans.map((l) => (
                <tr key={l.name} className={l.name === data.cheapest ? 'is-cheapest' : ''}>
                  <td>
                    {l.name}
                    {l.name === data.cheapest && <span className="tool__badge">cheapest</span>}
                  </td>
                  <td className="tabular">{formatMoney(Number(l.payment))}</td>
                  <td>
                    {l.payoff_date
                      ? `${formatDate(l.payoff_date)} (${l.months} mo)`
                      : 'never at this payment'}
                  </td>
                  <td className="tabular">{formatMoney(Number(l.total_interest))}</td>
                  <td className="tabular">{formatMoney(Number(l.total_cost))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="tool__aside">
            Total cost is the amount borrowed plus all interest plus fees — everything that leaves
            your pocket.
          </p>
        </div>
      )}
    </div>
  )
}
