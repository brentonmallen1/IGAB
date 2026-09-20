import { useState } from 'react'
import { Dialog } from '../../common/Dialog/Dialog'
import { apiErrorMessage } from '../../../api/client'
import { useTransferCandidates, useUpdateTransaction } from '../../../api/transactions'
import { useFormatters } from '../../../hooks/useFormatters'
import type { Account, Transaction } from '../../../types'
import {
  CREATE_NEW_PARTNER,
  awaitingPartnerChoice,
  transferLinkFields,
  transferTargets,
} from '../transferConversion'
import './MakeTransferDialog.css'

/**
 * Turn one register row into a transfer, without opening the editor.
 *
 * Two surfaces open it — the selection bar's "Make Transfer" and the inline
 * payee picker's "Transfer to account" group — and both hand it a row and,
 * from the picker, the account already chosen. What it asks is what the
 * server cannot answer on its own: which account, and (only when more than
 * one row over there could be it) which transaction is the far leg.
 *
 * One row at a time on purpose. The far-leg question is per row and only a
 * person can answer it; a bulk "make these six transfers" would either ask
 * six times in a trench coat or guess, and guessing links the wrong money
 * while looking authoritative (domain/transfers.pair_legs says the same
 * thing about the sync's own pairing).
 *
 * The request itself is `transferConversion.transferLinkFields` — the same
 * fields the editor sends, so a link made here is indistinguishable from one
 * made there.
 */
export function MakeTransferDialog({
  budgetId,
  transaction,
  accounts,
  initialAccountId = '',
  onClose,
}: {
  budgetId: string
  transaction: Transaction
  accounts: Account[]
  /** Pre-chosen when the picker already named the destination. */
  initialAccountId?: string
  onClose: () => void
}) {
  const { formatMoney } = useFormatters()
  const updateTxn = useUpdateTransaction(budgetId)
  const [accountId, setAccountId] = useState(initialAccountId)
  const [partnerChoice, setPartnerChoice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const targets = transferTargets(accounts, transaction.account_id)
  const target = targets.find((a) => a.id === accountId)
  const { data: candidates = [] } = useTransferCandidates(
    budgetId,
    accountId ? transaction.id : null,
    accountId || null
  )
  const needsChoice = awaitingPartnerChoice(candidates, partnerChoice)

  async function submit() {
    setError(null)
    try {
      await updateTxn.mutateAsync({
        id: transaction.id,
        ...transferLinkFields(accountId, partnerChoice),
      })
      onClose()
    } catch (err) {
      setError(apiErrorMessage(err, 'The transfer could not be linked'))
    }
  }

  function attempt() {
    if (!accountId) {
      setError('Pick the account this money moved to or from.')
      return
    }
    if (needsChoice) {
      setError(`Say which transaction in ${target?.name} is the other side.`)
      return
    }
    submit()
  }

  return (
    <Dialog
      title="Make this a transfer"
      historyKey="make-transfer"
      onClose={onClose}
      footer={
        <div className="dialog-actions">
          {/* Enabled, with the reason in the footer when it cannot go through
              — the dialog standard. A disabled button that will not say why
              is what sent the user to the editor in the first place. */}
          {error && <span className="dialog-form__error">{error}</span>}
          <div className="dialog-actions__end">
            <button className="dialog-btn dialog-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              className="dialog-btn dialog-btn--primary"
              onClick={attempt}
              disabled={updateTxn.isPending}
            >
              {updateTxn.isPending ? 'Linking…' : 'Make transfer'}
            </button>
          </div>
        </div>
      }
    >
      <div className="dialog-form">
        <p className="mtd__row">
          {transaction.date} · {formatMoney(transaction.amount)}
          {transaction.memo ? ` · ${transaction.memo}` : ''}
        </p>

        <label className="dialog-form__field">
          <span>{transaction.amount < 0 ? 'Money went to' : 'Money came from'}</span>
          <select
            autoFocus
            value={accountId}
            onChange={(e) => {
              setAccountId(e.target.value)
              setPartnerChoice(null)
              setError(null)
            }}
            aria-label="Transfer account"
          >
            <option value="">Select account…</option>
            {targets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>

        {/* More than one row over there could be this transfer's other half.
            Guessing would either link the wrong money or write a duplicate,
            so the answer is the user's. */}
        {candidates.length > 0 && (
          <div className="dialog-form__field">
            <span>Which transaction in {target?.name} is the other side?</span>
            {candidates.map((c) => (
              <label key={c.id} className="dialog-form__field--inline">
                <input
                  type="radio"
                  name="make-transfer-partner"
                  checked={partnerChoice === c.id}
                  onChange={() => {
                    setPartnerChoice(c.id)
                    setError(null)
                  }}
                />
                <span>
                  {c.date} · {formatMoney(c.amount)}
                  {c.memo ? ` · ${c.memo}` : ''}
                  {c.cleared === 'reconciled' ? ' · reconciled' : ''}
                </span>
              </label>
            ))}
            <label className="dialog-form__field--inline">
              <input
                type="radio"
                name="make-transfer-partner"
                checked={partnerChoice === CREATE_NEW_PARTNER}
                onChange={() => {
                  setPartnerChoice(CREATE_NEW_PARTNER)
                  setError(null)
                }}
              />
              <span>None of these — add the matching transaction to {target?.name}</span>
            </label>
          </div>
        )}
      </div>
    </Dialog>
  )
}
