import { parseAmountInput } from '../../utils/money'
import type { MinimumPaymentKind } from '../../api/liabilities'
import { useState } from 'react'
import toast from 'react-hot-toast'
import { useAccounts } from '../../api/accounts'
import { useAccountTypes } from '../../api/accountTypes'
import { liabilityTypeLabel } from '../../utils/liabilityTypeLabel'
import { isCardAccount } from '../../utils/accountKinds'
import {
  useCreateLiability,
  useLiabilities,
  useDeleteLiability,
  useUpdateLiability,
  type Liability,
  type LiabilityType,
} from '../../api/liabilities'
import './LiabilitySettingsModal.css'
import { confirmAsync } from '../../stores/confirmStore'
import { Dialog } from '../common/Dialog/Dialog'

const LIABILITY_TYPES: { value: LiabilityType; label: string }[] = [
  { value: 'mortgage', label: 'Mortgage' },
  { value: 'auto', label: 'Auto loan' },
  { value: 'student', label: 'Student loan' },
  { value: 'personal', label: 'Personal loan' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'medical', label: 'Medical' },
  { value: 'other', label: 'Other' },
]

/** The form lives in the scroll region; its submit button lives in the pinned
 *  footer, and `form=` is what joins them. */
const FORM_ID = 'liability-settings-form'

interface Props {
  budgetId: string
  liability: Liability | null // null = create
  onClose: () => void
  onDeleted?: () => void
}

/**
 * Create/edit a liability. The mode switch makes the managed-vs-unmanaged
 * exclusivity obvious: a liability tracks EITHER a real account's ledger OR a
 * manually entered balance — never both.
 */
export function LiabilitySettingsModal({ budgetId, liability, onClose, onDeleted }: Props) {
  const { data: accounts = [] } = useAccounts(budgetId)
  const { data: accountTypes } = useAccountTypes(budgetId)
  const { data: liabilities = [] } = useLiabilities(budgetId)
  const createLiability = useCreateLiability(budgetId)
  const updateLiability = useUpdateLiability(budgetId)
  const deleteLiability = useDeleteLiability(budgetId)

  const [name, setName] = useState(liability?.name ?? '')
  // Only meaningful for an unmanaged liability. A managed one reads its kind
  // from the linked account, and liability.liability_type is that resolved
  // account-type key — not one of these options.
  const [liabilityType, setLiabilityType] = useState<LiabilityType>(
    (liability?.mode === 'unmanaged' ? liability.liability_type : null) ?? 'personal'
  )
  const [mode, setMode] = useState<'managed' | 'unmanaged'>(liability?.mode ?? 'unmanaged')
  const [accountId, setAccountId] = useState(liability?.linked_account_id ?? '')
  const [balance, setBalance] = useState(
    liability && liability.mode === 'unmanaged' ? String(liability.current_balance) : ''
  )
  // Nullable since the terms became optional: String(null) would have shown a
  // literal "null" in the field a companion row is created to have filled in.
  const [rate, setRate] = useState(
    liability?.interest_rate != null ? String(liability.interest_rate) : ''
  )
  const [minimumPayment, setMinimumPayment] = useState(
    liability?.minimum_payment != null ? String(liability.minimum_payment) : ''
  )
  // A card's minimum is usually a rule, not a number. Default stays 'fixed' —
  // every liability entered before this existed is one, and nothing about it
  // changes.
  const [minimumKind, setMinimumKind] = useState<MinimumPaymentKind>(
    liability?.minimum_payment_kind ?? 'fixed'
  )
  const [minimumPercent, setMinimumPercent] = useState(
    liability?.minimum_payment_percent != null ? String(liability.minimum_payment_percent) : ''
  )
  const [minimumFloor, setMinimumFloor] = useState(
    liability?.minimum_payment_floor != null ? String(liability.minimum_payment_floor) : ''
  )
  const [minimumPlusInterest, setMinimumPlusInterest] = useState(
    liability?.minimum_payment_plus_interest ?? false
  )
  const [originationDate, setOriginationDate] = useState(liability?.origination_date ?? '')
  const [originalPrincipal, setOriginalPrincipal] = useState(
    liability?.original_principal != null ? String(liability.original_principal) : ''
  )
  const [termMonths, setTermMonths] = useState(
    liability?.term_months != null ? String(liability.term_months) : ''
  )
  const [promoEnabled, setPromoEnabled] = useState(liability?.promo_end_date != null)
  const [promoEndDate, setPromoEndDate] = useState(liability?.promo_end_date ?? '')
  const [promoDeferred, setPromoDeferred] = useState(liability?.promo_deferred_interest ?? false)
  const [dueDay, setDueDay] = useState(
    liability?.payment_due_day != null ? String(liability.payment_due_day) : ''
  )
  const [error, setError] = useState<string | null>(null)

  // A companion liability belongs to its account: the account is where it
  // lives, not a setting on it. Type is already read-only for that reason;
  // the account itself gets the same treatment — the modal opens from the
  // account's own page, and the old picker offered Checking and Savings.
  const isCompanion = liability !== null && liability.mode === 'managed'
  const ownAccount = accounts.find((a) => a.id === liability?.linked_account_id)
  // A card, by the accountKinds rule for a managed liability (accountId is
  // seeded from the link, so this tracks the form) or by the stored kind for
  // an unmanaged one. Cards get a bill due day; loans don't.
  const linkedAccount = accounts.find((a) => a.id === accountId)
  const isCard =
    mode === 'managed'
      ? linkedAccount !== undefined && isCardAccount(linkedAccount)
      : liabilityType === 'credit_card'

  // Creating: only accounts that are liabilities and are not already backing
  // another one.
  const linkedElsewhere = new Set(
    liabilities
      .filter((l) => l.id !== liability?.id && l.linked_account_id)
      .map((l) => l.linked_account_id)
  )
  const linkableAccounts = accounts.filter(
    (a) => a.classification === 'liability' && !linkedElsewhere.has(a.id)
  )

  const isPending =
    createLiability.isPending || updateLiability.isPending || deleteLiability.isPending

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return setError('Give this liability a name')
    // parseAmountInput, not parseFloat: a rate is typed by a person and so
    // carries the same separator conventions money does — "5,5" is 5.5.
    const rateNum = parseAmountInput(rate)
    if (isNaN(rateNum) || rateNum < 0) return setError('Enter a non-negative interest rate')
    // Never `|| 0` on a parsed amount: an unreadable figure has to surface,
    // and a silent zero here means "the debt never retires" in every
    // projection downstream.
    const paymentNum = parseAmountInput(minimumPayment)
    const percentNum = parseAmountInput(minimumPercent)
    const floorNum = parseAmountInput(minimumFloor)
    if (minimumKind === 'fixed') {
      if (isNaN(paymentNum) || paymentNum < 0) return setError('Enter the minimum monthly payment')
    } else {
      if (isNaN(percentNum) || percentNum <= 0) {
        return setError('Enter the percentage of the balance this card asks for')
      }
      // Not a nicety: without a floor the balance asymptotes and the debt
      // never clears, so every projection would be a curve to nowhere.
      if (isNaN(floorNum) || floorNum <= 0) {
        return setError('Enter the minimum dollar amount — without it the debt never pays off')
      }
    }
    if (mode === 'managed' && !isCompanion && !accountId)
      return setError('Choose the account this liability lives in')
    const balanceNum = parseAmountInput(balance)
    if (mode === 'unmanaged' && (isNaN(balanceNum) || balanceNum < 0)) {
      return setError('Enter the current balance owed')
    }
    setError(null)

    if (promoEnabled && !promoEndDate) {
      return setError('Enter the promo end date (or turn promotional financing off)')
    }
    const dueDayNum = dueDay ? parseInt(dueDay, 10) : null
    if (isCard && dueDayNum !== null && (isNaN(dueDayNum) || dueDayNum < 1 || dueDayNum > 31)) {
      return setError('The bill due day is a day of the month — 1 to 31')
    }

    const shared = {
      name: name.trim(),
      // Dropped server-side for a managed liability; omitted here so the two
      // never disagree about what was asked for.
      ...(mode === 'unmanaged' ? { liability_type: liabilityType } : {}),
      interest_rate: rateNum,
      minimum_payment_kind: minimumKind,
      minimum_payment: minimumKind === 'fixed' ? paymentNum : null,
      minimum_payment_percent: minimumKind === 'fixed' ? null : percentNum,
      minimum_payment_floor: minimumKind === 'fixed' ? null : floorNum,
      minimum_payment_plus_interest: minimumKind === 'fixed' ? false : minimumPlusInterest,
      origination_date: originationDate || null,
      original_principal: originalPrincipal ? parseAmountInput(originalPrincipal) : null,
      term_months: termMonths ? parseInt(termMonths, 10) : null,
      promo_end_date: promoEnabled ? promoEndDate : null,
      promo_deferred_interest: promoEnabled ? promoDeferred : false,
      // Null for a loan on purpose: retyping a card to a loan clears the day
      // rather than leaving a stale one behind.
      payment_due_day: isCard ? dueDayNum : null,
    }

    try {
      if (liability) {
        await updateLiability.mutateAsync({
          liabilityId: liability.id,
          ...shared,
          // A companion's account is not sent at all: it cannot change here.
          ...(isCompanion
            ? {}
            : mode === 'managed'
              ? { linked_account_id: accountId }
              : { linked_account_id: null, manual_balance: balanceNum }),
        })
      } else {
        await createLiability.mutateAsync({
          ...shared,
          ...(mode === 'managed'
            ? { linked_account_id: accountId }
            : { manual_balance: balanceNum }),
        })
      }
      toast.success(liability ? 'Liability updated' : `Now tracking ${name.trim()}`)
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Save failed')
    }
  }

  async function handleDelete() {
    if (!liability) return
    const ok = await confirmAsync({
      title: `Stop tracking "${liability.name}"?`,
      message: "This won't touch any accounts or transactions.",
      confirmLabel: 'Stop tracking',
      destructive: true,
    })
    if (!ok) return
    await deleteLiability.mutateAsync(liability.id)
    toast.success('Liability removed')
    onClose()
    onDeleted?.()
  }

  return (
    <Dialog
      title={liability ? 'Liability settings' : 'Track a liability'}
      onClose={onClose}
      historyKey="liability-settings"
      className="liability-modal"
      footer={
        <>
          {liability ? (
            <button
              type="button"
              className="liability-modal__btn liability-modal__btn--danger"
              onClick={handleDelete}
              disabled={isPending}
            >
              Delete
            </button>
          ) : (
            <span />
          )}
          <div className="liability-modal__actions">
            <button
              type="button"
              className="liability-modal__btn liability-modal__btn--secondary"
              onClick={onClose}
              disabled={isPending}
            >
              Cancel
            </button>
            {/* The footer is pinned outside the form, so the submit button
                reaches it by id rather than by containment. */}
            <button
              type="submit"
              form={FORM_ID}
              className="liability-modal__btn liability-modal__btn--primary"
              disabled={isPending}
            >
              {isPending ? 'Saving…' : liability ? 'Save' : 'Start tracking'}
            </button>
          </div>
        </>
      }
    >
      <form id={FORM_ID} className="liability-modal__body" onSubmit={handleSubmit}>
        <label className="liability-modal__field">
          <span>Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            placeholder="Car loan"
          />
        </label>

        <div className="liability-modal__row">
          {mode === 'unmanaged' ? (
            <label className="liability-modal__field">
              <span>Type</span>
              <select
                value={liabilityType}
                onChange={(e) => setLiabilityType(e.target.value as LiabilityType)}
              >
                {LIABILITY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="liability-modal__field">
              <span>Type</span>
              <input
                type="text"
                value={liabilityTypeLabel(liability?.liability_type, accountTypes)}
                readOnly
                title="Set by the linked account's type — change it on the account"
              />
            </label>
          )}
          <label className="liability-modal__field">
            <span>Interest rate (% / yr)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.001"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              placeholder="6.25"
            />
          </label>
          {/* In this row because it is the same shape as its neighbours — one
              short input. The minimum-payment rule below is not, which is why
              it gets the full width instead of a third of it. */}
          {isCard && (
            <label className="liability-modal__field">
              <span>Bill due day</span>
              <input
                type="number"
                inputMode="numeric"
                min="1"
                max="31"
                value={dueDay}
                onChange={(e) => setDueDay(e.target.value)}
                placeholder="17"
                title="Shown on the card page — a reminder, not a projection input"
              />
            </label>
          )}
        </div>

        <div className="liability-modal__field">
          <span>Minimum payment</span>
          <div
            className="liability-modal__segmented"
            role="radiogroup"
            aria-label="Minimum payment"
          >
            <button
              type="button"
              role="radio"
              aria-checked={minimumKind === 'fixed'}
              className={minimumKind === 'fixed' ? 'is-selected' : ''}
              onClick={() => setMinimumKind('fixed')}
            >
              A fixed amount
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={minimumKind === 'percent_of_balance'}
              className={minimumKind === 'percent_of_balance' ? 'is-selected' : ''}
              onClick={() => setMinimumKind('percent_of_balance')}
            >
              A percentage of the balance
            </button>
          </div>
          {minimumKind === 'fixed' ? (
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={minimumPayment}
              onChange={(e) => setMinimumPayment(e.target.value)}
              placeholder="275.00"
              aria-label="Minimum payment amount"
            />
          ) : (
            <div className="liability-modal__rule">
              <label>
                <span>Percent of balance</span>
                {/* Placeholders, not values: a guessed number that looks
                        entered is worse than a blank one. */}
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  value={minimumPercent}
                  onChange={(e) => setMinimumPercent(e.target.value)}
                  placeholder="2"
                />
              </label>
              <label>
                <span>But at least</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  value={minimumFloor}
                  onChange={(e) => setMinimumFloor(e.target.value)}
                  placeholder="35.00"
                />
              </label>
              <label className="liability-modal__rule-check">
                <input
                  type="checkbox"
                  checked={minimumPlusInterest}
                  onChange={(e) => setMinimumPlusInterest(e.target.checked)}
                />
                <span>plus this month&rsquo;s interest</span>
              </label>
            </div>
          )}
        </div>

        {isCompanion ? (
          <label className="liability-modal__field">
            <span>Account</span>
            <input
              type="text"
              value={ownAccount?.name ?? ''}
              readOnly
              title="Set by the account this liability lives in — its balance and payments come from that ledger"
            />
          </label>
        ) : (
          <fieldset className="liability-modal__mode">
            <legend>Where does the balance come from?</legend>
            <label
              className={`liability-modal__mode-option ${mode === 'managed' ? 'liability-modal__mode-option--active' : ''}`}
            >
              <input
                type="radio"
                name="liability-mode"
                checked={mode === 'managed'}
                onChange={() => setMode('managed')}
              />
              <span>
                <strong>An account in this budget</strong>
                <small>Balance and payments track the account's ledger automatically</small>
              </span>
            </label>
            <label
              className={`liability-modal__mode-option ${mode === 'unmanaged' ? 'liability-modal__mode-option--active' : ''}`}
            >
              <input
                type="radio"
                name="liability-mode"
                checked={mode === 'unmanaged'}
                onChange={() => setMode('unmanaged')}
              />
              <span>
                <strong>I'll enter it myself</strong>
                <small>
                  For liabilities without an account here — update the balance as you pay
                </small>
              </span>
            </label>

            {mode === 'managed' ? (
              <label className="liability-modal__field liability-modal__mode-detail">
                <span>Account</span>
                <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                  <option value="" disabled>
                    Choose an account…
                  </option>
                  {linkableAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="liability-modal__field liability-modal__mode-detail">
                <span>Current balance owed</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min="0"
                  step="0.01"
                  value={balance}
                  onChange={(e) => setBalance(e.target.value)}
                  placeholder="9480.00"
                />
              </label>
            )}
          </fieldset>
        )}

        <details className="liability-modal__optional">
          <summary>Loan details — enables progress &amp; term insights</summary>
          <div className="liability-modal__row">
            <label className="liability-modal__field">
              <span>Origination date</span>
              <input
                type="date"
                value={originationDate}
                onChange={(e) => setOriginationDate(e.target.value)}
              />
            </label>
            <label className="liability-modal__field">
              <span>Original principal</span>
              <input
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                value={originalPrincipal}
                onChange={(e) => setOriginalPrincipal(e.target.value)}
              />
            </label>
            <label className="liability-modal__field">
              <span>Term (months)</span>
              <input
                type="number"
                inputMode="numeric"
                min="1"
                step="1"
                value={termMonths}
                onChange={(e) => setTermMonths(e.target.value)}
                placeholder="360"
              />
            </label>
          </div>

          <label className="liability-modal__promo-toggle">
            <input
              type="checkbox"
              checked={promoEnabled}
              onChange={(e) => setPromoEnabled(e.target.checked)}
            />
            <span>
              <strong>Promotional financing</strong>
              <small>0% interest until a deadline — the rate above applies after it</small>
            </span>
          </label>
          {promoEnabled && (
            <div className="liability-modal__row">
              <label className="liability-modal__field">
                <span>Promo ends</span>
                <input
                  type="date"
                  value={promoEndDate}
                  onChange={(e) => setPromoEndDate(e.target.value)}
                />
              </label>
              <label className="liability-modal__promo-toggle liability-modal__promo-toggle--sub">
                <input
                  type="checkbox"
                  checked={promoDeferred}
                  onChange={(e) => setPromoDeferred(e.target.checked)}
                />
                <span>
                  <strong>Deferred interest</strong>
                  <small>Missing the deadline charges interest retroactively</small>
                </span>
              </label>
            </div>
          )}
        </details>

        {error && <div className="liability-modal__error">{error}</div>}
      </form>
    </Dialog>
  )
}
