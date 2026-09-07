import { useMemo, useState } from 'react'
import { useFormatters } from '../../../hooks/useFormatters'
import { parseAmountInput } from '../../../utils/money'
import { compareTransfer } from './balanceTransferMath'

function num(raw: string, fallback = 0): number {
  const n = parseAmountInput(raw)
  return Number.isNaN(n) ? fallback : n
}

/** Stay put or transfer — the fee against the interest avoided, and what is
 *  left when the promo ends. Pure arithmetic in balanceTransferMath.ts. */
export function BalanceTransfer() {
  const { formatMoney } = useFormatters()
  const [balance, setBalance] = useState('')
  const [currentApr, setCurrentApr] = useState('24')
  const [payment, setPayment] = useState('')
  const [feePercent, setFeePercent] = useState('3')
  const [promoMonths, setPromoMonths] = useState('15')
  const [postPromoApr, setPostPromoApr] = useState('27')

  const result = useMemo(() => {
    const b = num(balance)
    const p = num(payment)
    if (b <= 0 || p <= 0) return null
    return compareTransfer({
      balance: b,
      currentApr: num(currentApr),
      payment: p,
      feePercent: num(feePercent),
      promoMonths: Math.max(0, Math.round(num(promoMonths))),
      promoApr: 0,
      postPromoApr: num(postPromoApr),
    })
  }, [balance, currentApr, payment, feePercent, promoMonths, postPromoApr])

  const months = (m: number | null) => (m === null ? 'never at this payment' : `${m} months`)

  const field = (
    label: string,
    value: string,
    set: (v: string) => void,
    props: Record<string, string> = {}
  ) => (
    <label className="tool__field">
      <span>{label}</span>
      <input
        type="number"
        inputMode="decimal"
        min="0"
        step="0.01"
        value={value}
        onChange={(e) => set(e.target.value)}
        {...props}
      />
    </label>
  )

  return (
    <div className="tool">
      <div className="tool__inputs tool__grid">
        {field('Balance to move', balance, setBalance, { placeholder: '2400' })}
        {field('Current card APR %', currentApr, setCurrentApr)}
        {field('Monthly payment', payment, setPayment, { placeholder: '200' })}
        {field('Transfer fee %', feePercent, setFeePercent, { step: '0.1' })}
        {field('0% promo months', promoMonths, setPromoMonths, { step: '1', inputMode: 'numeric' })}
        {field('APR after the promo %', postPromoApr, setPostPromoApr)}
      </div>

      {result ? (
        <div className="tool__results">
          <div className="tool__cards">
            <div className="tool__card">
              <div className="tool__card-title">Stay where it is</div>
              <dl className="tool__facts">
                <div>
                  <dt>Paid off in</dt>
                  <dd>{months(result.stay.months)}</dd>
                </div>
                <div>
                  <dt>Interest paid</dt>
                  <dd>{formatMoney(result.stay.interest)}</dd>
                </div>
              </dl>
            </div>
            <div className={`tool__card ${result.saving > 0 ? 'tool__card--strategy' : ''}`}>
              <div className="tool__card-title">Transfer</div>
              <dl className="tool__facts">
                <div>
                  <dt>Fee up front</dt>
                  <dd>{formatMoney(result.transfer.fee)}</dd>
                </div>
                <div>
                  <dt>Paid off in</dt>
                  <dd>{months(result.transfer.months)}</dd>
                </div>
                <div>
                  <dt>Interest paid</dt>
                  <dd>{formatMoney(result.transfer.interest)}</dd>
                </div>
                {result.transfer.balanceAtPromoEnd !== undefined && (
                  <div>
                    <dt>Left when the promo ends</dt>
                    <dd>{formatMoney(result.transfer.balanceAtPromoEnd)}</dd>
                  </div>
                )}
              </dl>
            </div>
          </div>
          <p className="tool__summary">
            {result.saving > 0
              ? `Transferring costs ${formatMoney(result.saving)} less overall (interest plus the fee).`
              : result.saving < 0
                ? `Transferring costs ${formatMoney(-result.saving)} more overall — the fee outweighs the interest avoided at this payment.`
                : 'It comes out even.'}
          </p>
          <p className="tool__hint">
            The trap is the end date: whatever is left when the promo expires is charged at the new
            card&apos;s ordinary rate. A deferred-interest offer charges interest on the whole
            original amount if any is left — this calculator assumes a true 0% promo.
          </p>
        </div>
      ) : (
        <p className="tool__hint">Enter the balance and the payment you will make each month.</p>
      )}
    </div>
  )
}
